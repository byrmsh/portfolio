import json
import logging
import re
import sys
import time
from operator import itemgetter
from pathlib import Path
from typing import Awaitable, Callable, List, Optional

import structlog
from curl_cffi import requests
from curl_cffi.requests import ProxySpec, Session
from curl_cffi.requests.exceptions import HTTPError, ProxyError
from environs import env
from redis import Redis
from redis.exceptions import ResponseError as RedisResponseError
from simple_pid import PID

from typex import (
    ClientConfValidator,
    HeadersValidator,
    InitialLoginPayloadValidator,
    LoginResponse,
    UpworkJobResult,
    UpworkJobSearchResponse,
)

env.read_env(recurse=False)

_HERE = Path(__file__).resolve().parent
JOB_SEARCH_QUERY = (_HERE / "job-search.gql").read_text("utf-8")
CONNECTS_FREELANCER_QUERY = (_HERE / "connects-freelancer.gql").read_text("utf-8")
REDIS_URL = env.str("REDIS_URL")
STREAM_KEY = env.str("REDIS_STREAM_KEY", default="jobs")
UPWORK_TOKEN_REDIS_KEY = env.str("UPWORK_TOKEN_REDIS_KEY", default="upwork_token")
MAX_OFFSET = 5000
MAX_PAGE_SIZE = 50
OPTIMAL_PAGE_SIZE = env.int("OPTIMAL_PAGE_SIZE", default=40)
DEFAULT_FETCH_INTERVAL_SECONDS = env.int("DEFAULT_FETCH_INTERVAL_SECONDS", default=600)
UPWORK_BEARER_TOKEN = env.str("UPWORK_BEARER_TOKEN", default="").strip()
# Upwork doesn't expose connects pricing on job search results anymore; fetch it separately when desired.
FETCH_CONNECTS_DATA = env.bool("FETCH_CONNECTS_DATA", default=True)
COMMON_HEADERS_RAW = env.str("COMMON_HEADERS", default="")
LOGIN_HEADERS_RAW = env.str("LOGIN_HEADERS", default="")
GRAPHQL_HEADERS_RAW = env.str("GRAPHQL_HEADERS", default="")
LOGIN_DATA_RAW = env.str("LOGIN_DATA", default="")
COMMON_HEADERS = (
    HeadersValidator.validate_json(COMMON_HEADERS_RAW) if COMMON_HEADERS_RAW else {}
)
LOGIN_HEADERS = (
    HeadersValidator.validate_json(LOGIN_HEADERS_RAW) if LOGIN_HEADERS_RAW else {}
)
GRAPHQL_HEADERS = (
    HeadersValidator.validate_json(GRAPHQL_HEADERS_RAW) if GRAPHQL_HEADERS_RAW else {}
)
LOGIN_DATA = (
    InitialLoginPayloadValidator.validate_json(LOGIN_DATA_RAW)
    if LOGIN_DATA_RAW
    else None
)
PROXY_URL = env.str("PROXY_URL", default="")
PROXY_LIST_FILE = env.str("PROXY_LIST_FILE", default="")
def load_proxy_urls() -> List[str]:
    proxies: List[str] = []
    if PROXY_LIST_FILE:
        proxy_file_path = Path(PROXY_LIST_FILE)
        if not proxy_file_path.exists():
            raise ValueError(f"PROXY_LIST_FILE does not exist: {PROXY_LIST_FILE}")
        proxy_lines = proxy_file_path.read_text("utf-8").splitlines()
        proxies.extend(
            line.strip()
            for line in proxy_lines
            if line.strip() and not line.lstrip().startswith("#")
        )
    if PROXY_URL:
        proxies.append(PROXY_URL)
    return proxies


PROXY_URLS = load_proxy_urls()
_proxy_index = 0
DEFAULT_PROXY_MAX_RETRIES = max(5, min(len(PROXY_URLS), 20))


def next_proxies() -> Optional[ProxySpec]:
    if not PROXY_URLS:
        return None
    global _proxy_index
    proxy_url = PROXY_URLS[_proxy_index % len(PROXY_URLS)]
    _proxy_index += 1
    return {"http": proxy_url, "https": proxy_url}

logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()
r = Redis.from_url(REDIS_URL, decode_responses=True)
logger.info(
    "Proxy configuration loaded",
    proxy_count=len(PROXY_URLS),
    proxy_list_file=PROXY_LIST_FILE or None,
    direct_connection=not PROXY_URLS,
)


class UnauthorizedError(HTTPError):
    pass


class ProxyForbiddenError(HTTPError):
    pass


def login_to_account_sec(
    session: Session, sec_check_data: Optional[dict] = None
) -> LoginResponse:
    if LOGIN_DATA is None:
        raise ValueError(
            "LOGIN_DATA is required for automated login. "
            "Set UPWORK_BEARER_TOKEN to skip login flow."
        )
    logger.info("Logging in")
    url = "https://www.upwork.com/ab/account-security/login"
    static_headers = {
        "accept": "*/*",
        "origin": "https://www.upwork.com",
        "referer": "https://www.upwork.com/ab/account-security/login",
        "x-requested-with": "XMLHttpRequest",
    }
    headers = COMMON_HEADERS | LOGIN_HEADERS | static_headers
    json_data = {"login": LOGIN_DATA["login"] | (sec_check_data or {})}
    res = session.post(url, json=json_data, headers=headers, proxies=next_proxies())
    raise_custom_http_errors(res)
    return res.json()


def raise_custom_http_errors(res: requests.Response):
    if res.status_code == 401:
        raise UnauthorizedError("Unauthorized", response=res)
    if res.status_code == 403:
        # This may be a proxy-level 403, a Cloudflare/anti-bot response, or an account restriction.
        # Treat as retryable only when using proxies.
        if PROXY_URLS:
            raise ProxyForbiddenError("Forbidden (proxy or Cloudflare)", response=res)
    res.raise_for_status()


def request_and_parse_token(session: Session) -> str:
    params = {"page": "2"}
    url = "https://www.upwork.com/nx/search/jobs"
    static_headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "upgrade-insecure-requests": "1",
        "sec-fetch-user": "?1",
    }
    headers = COMMON_HEADERS | static_headers
    res = session.get(url, params=params, headers=headers, proxies=next_proxies())
    raise_custom_http_errors(res)
    match = re.search(r"(?<=clientConf\=)\{[^}]+}", res.text)
    if not match:
        raise HTTPError("Failed to find clientConf in jobs response", response=res)
    client_conf = ClientConfValidator.validate_json(match.group())
    return client_conf["token"]


def retry_until_not_forbidden(
    func: Callable, args=(), max_retries: Optional[int] = None
):
    if not PROXY_URLS:
        # No proxy rotation; retries here don't help and can amplify rate-limits.
        return func(*args)
    retries = max_retries or DEFAULT_PROXY_MAX_RETRIES
    for attempt in range(1, retries):
        try:
            return func(*args)
        except ProxyForbiddenError as e:
            logger.warning(
                "Forbidden error, retrying",
                attempt=attempt,
                max_retries=retries,
                error=str(e),
            )
            time.sleep(min(2, 0.25 * attempt))
        except ProxyError as e:
            logger.warning(
                "Proxy transport error, retrying",
                attempt=attempt,
                max_retries=retries,
                error=str(e),
            )
            time.sleep(min(2, 0.25 * attempt))
    return func(*args)


def cache_authorized_token() -> str:
    with requests.Session() as session:
        res = retry_until_not_forbidden(login_to_account_sec, (session,))
        if not res.get("success") and res.get("authToken"):
            sec_check_fields = ["authToken", "securityCheckCertificate"]
            sec_check_data = {k: res[k] for k in sec_check_fields}
            logger.info("Need to complete security check for login", **sec_check_data)
            retry_until_not_forbidden(login_to_account_sec, (session, sec_check_data))
        token = retry_until_not_forbidden(request_and_parse_token, (session,))
        r.set(UPWORK_TOKEN_REDIS_KEY, token)
        return token


def normalize_bearer_token(token: str) -> str:
    token = token.strip()
    if not token:
        return token
    if token.lower().startswith("bearer "):
        return token.split(None, 1)[1].strip()
    return token


def get_authorization_token() -> str:
    if UPWORK_BEARER_TOKEN:
        return normalize_bearer_token(UPWORK_BEARER_TOKEN)
    # Allow supplying a full captured browser header set via GRAPHQL_HEADERS only.
    hdr_token = GRAPHQL_HEADERS.get("authorization") or GRAPHQL_HEADERS.get("Authorization")
    if hdr_token:
        return normalize_bearer_token(hdr_token)
    token = r.get(UPWORK_TOKEN_REDIS_KEY)
    if token:
        assert isinstance(token, str), f"Expected string for token, got {type(token)}"
        return normalize_bearer_token(token)
    return retry_until_not_forbidden(cache_authorized_token)


def fetch_jobs_endpoint(offset: int, count: int, token: str) -> UpworkJobSearchResponse:
    logger.info("Fetching jobs", offset=offset, count=count)
    if offset > MAX_OFFSET:
        raise ValueError("Offset can't be greater than {}", MAX_OFFSET)
    if count > MAX_PAGE_SIZE:
        raise ValueError("Count can't be greater than {}", MAX_PAGE_SIZE)
    params = {"alias": "userJobSearch"}
    data = {
        "query": JOB_SEARCH_QUERY,
        "variables": {
            "requestVariables": {
                # Frontend sends this even when empty; keep it to match the current contract.
                "userQuery": "",
                "sort": "recency",
                "highlight": True,
                "paging": {
                    "offset": offset,
                    "count": count,
                },
            },
        },
    }
    url = "https://www.upwork.com/api/graphql/v1"
    custom_headers = {
        "authorization": f"bearer {token}",
        "origin": "https://www.upwork.com",
        "referer": "https://www.upwork.com/nx/search/jobs",
    }
    headers = COMMON_HEADERS | GRAPHQL_HEADERS | custom_headers
    res = requests.post(
        url,
        params=params,
        headers=headers,
        json=data,
        proxies=next_proxies(),
    )
    raise_custom_http_errors(res)
    res_json = res.json()
    if "errors" in res_json:
        logger.warning("Errors in response", errors=res_json["errors"])
    logger.debug("Queried Upwork job search GraphQL endpoint", response=res_json)
    return res_json


def extract_job_entries(res: UpworkJobSearchResponse) -> List[UpworkJobResult]:
    if "data" not in res:
        # Upwork GraphQL returns "errors" (and no "data") for schema/query validation failures.
        errors = res.get("errors")
        hint = ""
        if errors and any(
            "oAuth2 client does not have permission" in (e.get("message") or "")
            for e in errors
            if isinstance(e, dict)
        ):
            hint = (
                " Hint: your token/headers are likely not the same as the Upwork web app. "
                "Capture the GraphQL request headers from your browser (Authorization and often Cookie/"
                "x-oauth2-client-id/etc) and set UPWORK_BEARER_TOKEN plus GRAPHQL_HEADERS."
            )
        raise RuntimeError(
            "Upwork GraphQL response missing 'data'. "
            f"Likely query/schema mismatch or auth/permissions issue. errors={errors!r}.{hint}"
        )
    return res["data"]["search"]["universalSearchNuxt"]["userJobSearchV1"]["results"]


def fetch_connects_data_for_job(job_id: str, token: str) -> dict:
    params = {"alias": "connectsDataForFreelancer"}
    data = {"query": CONNECTS_FREELANCER_QUERY, "variables": {"jobId": job_id}}
    url = "https://www.upwork.com/api/graphql/v1"
    custom_headers = {
        "authorization": f"Bearer {token}",
        "origin": "https://www.upwork.com",
        "referer": f"https://www.upwork.com/nx/search/jobs/details/{job_id}",
    }
    headers = COMMON_HEADERS | GRAPHQL_HEADERS | custom_headers
    res = requests.post(
        url,
        params=params,
        headers=headers,
        json=data,
        proxies=next_proxies(),
    )
    raise_custom_http_errors(res)
    res_json = res.json()
    if "errors" in res_json:
        logger.warning(
            "Errors in connects response", job_id=job_id, errors=res_json["errors"]
        )
    return res_json


def fetch_jobs_page(offset: int, count: int) -> List[UpworkJobResult]:
    token = get_authorization_token()
    try:
        res = retry_until_not_forbidden(fetch_jobs_endpoint, (offset, count, token))
    except UnauthorizedError as e:
        logger.info("Token expired, reauthorizing", error=str(e))
        token = retry_until_not_forbidden(cache_authorized_token)
        res = retry_until_not_forbidden(fetch_jobs_endpoint, (offset, count, token))
    return extract_job_entries(res)


def fetch_new_jobs(latest_job_id: int | None) -> List[UpworkJobResult]:
    logger.info("Starting fetch_new_jobs", latest_job_id=latest_job_id)
    if latest_job_id is None:
        return fetch_jobs_page(0, MAX_PAGE_SIZE)
    offset = 0
    new_job_entries = []
    while True:
        jobs = fetch_jobs_page(offset, MAX_PAGE_SIZE)
        filtered = [job for job in jobs if int(job["id"]) > latest_job_id]
        logger.info(
            "Processing page", offset=offset, fetched=len(jobs), filtered=len(filtered)
        )
        if not filtered:
            break
        new_job_entries.extend(filtered)
        if len(filtered) < MAX_PAGE_SIZE:
            break
        offset += MAX_PAGE_SIZE
    logger.info("Total new jobs fetched", total=len(new_job_entries))
    return new_job_entries


def get_latest_redis_job_id() -> int | None:
    last_entries = r.xrevrange(STREAM_KEY, count=1)
    assert not isinstance(last_entries, Awaitable)
    if last_entries:
        stream_id = last_entries[0][0]
        entry_id, _ = stream_id.split("-")
        return int(entry_id)
    return None


def add_jobs_to_redis(jobs: List[UpworkJobResult]) -> None:
    jobs_sorted = sorted(jobs, key=itemgetter("id"))
    logger.info("Adding jobs to redis", count=len(jobs_sorted))
    for job in jobs_sorted:
        try:
            job_id = job["id"]
            job_key = f"job:{job_id}"
            r.set(job_key, json.dumps(job))
            connects_data = job.get("connectsData")
            if connects_data is not None:
                r.set(f"job:{job_id}:connects", json.dumps(connects_data))
            stream_id = f"{job_id}-0"
            r.xadd(
                STREAM_KEY,
                {
                    "job_id": job_id,
                    "published_at": job["jobTile"]["job"]["publishTime"],
                    "fetched_at": str(int(time.time())),
                },
                stream_id,
            )
        except RedisResponseError as e:
            logger.warning(
                "Failed to add job to redis, skipping",
                job_id=job["id"],
                error=str(e),
            )


def process_jobs_iteration() -> int:
    latest_job_id = get_latest_redis_job_id()
    logger.info("Latest job id from redis", latest_job_id=latest_job_id)
    new_jobs = fetch_new_jobs(latest_job_id)
    logger.info("Jobs fetched from iteration", new_jobs=len(new_jobs))
    if new_jobs and FETCH_CONNECTS_DATA:
        token = get_authorization_token()
        for job in new_jobs:
            job_id = job["id"]
            try:
                try:
                    connects_res = retry_until_not_forbidden(
                        fetch_connects_data_for_job, (job_id, token)
                    )
                except UnauthorizedError:
                    if UPWORK_BEARER_TOKEN:
                        raise
                    token = retry_until_not_forbidden(cache_authorized_token)
                    connects_res = retry_until_not_forbidden(
                        fetch_connects_data_for_job, (job_id, token)
                    )
                job["connectsData"] = connects_res.get("data") or connects_res
            except Exception as e:
                logger.warning(
                    "Failed to fetch connects data", job_id=job_id, error=str(e)
                )
    if new_jobs:
        with r.lock("job_db_lock", timeout=10):
            add_jobs_to_redis(new_jobs)
    return len(new_jobs)


def sleep_by_pid_and_new_count(pid: PID, new_count: int) -> None:
    delay = pid(new_count - OPTIMAL_PAGE_SIZE) or DEFAULT_FETCH_INTERVAL_SECONDS
    logger.info("Sleeping for next fetch", delay=delay)
    time.sleep(delay)


def main():
    logger.info("Starting main fetch loop")
    pid = PID(0.1, 0.05, 0.01, setpoint=0, output_limits=(1, 3600))

    while True:
        new_count = process_jobs_iteration()
        logger.info("Iteration complete", new_jobs_fetched=new_count)
        sleep_by_pid_and_new_count(pid, new_count)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Unexpected error", exc_info=e)
        exit(1)
