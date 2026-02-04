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
from curl_cffi.requests.exceptions import HTTPError
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

JOB_SEARCH_QUERY = Path("job-search.gql").read_text("utf-8")
REDIS_URL = env.str("REDIS_URL")
STREAM_KEY = env.str("REDIS_STREAM_KEY", default="jobs")
UPWORK_TOKEN_REDIS_KEY = env.str("UPWORK_TOKEN_REDIS_KEY", default="upwork_token")
MAX_OFFSET = 5000
MAX_PAGE_SIZE = 50
OPTIMAL_PAGE_SIZE = env.int("OPTIMAL_PAGE_SIZE", default=40)
DEFAULT_FETCH_INTERVAL_SECONDS = env.int("DEFAULT_FETCH_INTERVAL_SECONDS", default=600)
LOGIN_DATA = InitialLoginPayloadValidator.validate_python(env.json("LOGIN_DATA"))
COMMON_HEADERS = HeadersValidator.validate_python(env.json("COMMON_HEADERS"))
LOGIN_HEADERS = HeadersValidator.validate_python(env.json("LOGIN_HEADERS"))
GRAPHQL_HEADERS = HeadersValidator.validate_python(env.json("GRAPHQL_HEADERS"))
PROXY_URL = env.str("PROXY_URL")
PROXIES: ProxySpec = {"https": PROXY_URL}

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


class UnauthorizedError(HTTPError):
    pass


class ProxyForbiddenError(HTTPError):
    pass


def login_to_account_sec(
    session: Session, sec_check_data: Optional[dict] = None
) -> LoginResponse:
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
    res = session.post(url, json=json_data, headers=headers, proxies=PROXIES)
    raise_custom_http_errors(res)
    return res.json()


def raise_custom_http_errors(res: requests.Response):
    if res.status_code == 401:
        raise UnauthorizedError("Unauthorized", response=res)
    if res.status_code == 403:
        raise ProxyForbiddenError("Proxy Cloudflare forbidden", response=res)
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
    res = session.get(url, params=params, headers=headers, proxies=PROXIES)
    raise_custom_http_errors(res)
    match = re.search(r"(?<=clientConf\=)\{[^}]+}", res.text)
    if not match:
        raise HTTPError("Failed to find clientConf in jobs response", response=res)
    client_conf = ClientConfValidator.validate_json(match.group())
    return client_conf["token"]


def retry_until_not_forbidden(func: Callable, args=(), max_retries=5):
    for _ in range(max_retries - 1):
        try:
            return func(*args)
        except ProxyForbiddenError as e:
            logger.warning("Forbidden error, retrying", exc_info=e)
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
    res = requests.post(url, params=params, headers=headers, json=data)
    raise_custom_http_errors(res)
    res_json = res.json()
    if "errors" in res_json:
        logger.warning("Errors in response", errors=res_json["errors"])
    logger.debug("Queried Upwork job search GraphQL endpoint", response=res_json)
    return res_json


def extract_job_entries(res: UpworkJobSearchResponse) -> List[UpworkJobResult]:
    return res["data"]["search"]["universalSearchNuxt"]["userJobSearchV1"]["results"]


def fetch_jobs_page(offset: int, count: int) -> List[UpworkJobResult]:
    token = r.get(UPWORK_TOKEN_REDIS_KEY)
    if not token:
        token = retry_until_not_forbidden(cache_authorized_token)
    assert isinstance(token, str), f"Expected string for token, got {type(token)}"
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
