# Upworker

Upworker is a lightweight worker for ingesting Upwork job data into Redis.

## Local Setup (uv)

1. Create a virtual environment and install deps:

```bash
uv venv
uv sync
```

2. Copy env sample:

```bash
cp .env.sample .env
```

3. Run the worker:

```bash
uv run upworker
```

## Proxy Configuration

- `PROXY_URL`: single proxy endpoint (good for rotating proxy providers).
- `PROXY_LIST_FILE`: path to a text file with one proxy URL per line.
- You can set either one; if both are set, both sources are used in round-robin order.
- If both are empty, Upworker will connect directly (no proxy).

## Authentication Notes

Upworker supports two modes:

1. Recommended: set `UPWORK_BEARER_TOKEN` and skip automated login.
2. Automated login: set `LOGIN_DATA` (and optional `LOGIN_HEADERS`) to fetch/refresh a token.

If you are getting blocked by Cloudflare challenges, prefer `UPWORK_BEARER_TOKEN` and avoid
proxy-based "bypass" approaches.

### Permissions / "oAuth2 client does not have permission"

If Upwork responds with a GraphQL error like:

- `Requested oAuth2 client does not have permission to see some of the requested fields`

then your `UPWORK_BEARER_TOKEN` (or your request headers) are not the same as what the Upwork
web app uses.

Practical fix:

- Capture the `Authorization: Bearer ...` header from your browser's job search GraphQL request.
- If the browser request also includes cookies or extra headers (ex: `x-oauth2-client-id`),
  copy them into `UPWORK_COOKIE` / `GRAPHQL_HEADERS`.

Environment variables:

- `UPWORK_COOKIE`: copied `Cookie` header value (optional, but sometimes required).
- `GRAPHQL_HEADERS`: JSON dict of additional headers to send to GraphQL (optional).

## Job Search Tuning

- `UPWORK_USER_QUERY`: optional search query string (maps to `userQuery` in `UserJobSearchV1Request`).
- `UPWORK_SORT`: sort string (default `recency`; browser often uses `relevance+desc`).

## Connects Data (Optional)

Job search results no longer expose connects pricing directly. Upworker can fetch connects data
per job via a separate GraphQL query and store it at `job:{id}:connects`.

- Enable with `FETCH_CONNECTS_DATA=true`.

### Optional pre-filter step (bash + curl)

Use the included script to build a clean proxy file once (or on a schedule), instead of checking on every worker start:

```bash
./scripts/check-proxies.sh ./proxies.txt ./proxies.good.txt
```

Then set:

```env
PROXY_LIST_FILE="./proxies.good.txt"
```

## Redis Stream Notes

Upworker writes full job JSON to `job:{id}` keys and emits a lightweight entry to the Redis
stream defined by `REDIS_STREAM_KEY` (default `jobs`). Each stream entry ID is the Upwork
job ID plus a `-0` suffix to match Redis stream ID format.
