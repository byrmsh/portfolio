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
3. Playwright bootstrap: set `UPWORK_AUTH_STRATEGY=playwright` to open a real browser and wait
   until the first successful Upwork GraphQL request, then reuse that token/headers.

If you are getting blocked by Cloudflare challenges, prefer `UPWORK_BEARER_TOKEN` and avoid
proxy-based "bypass" approaches.

### Playwright Bootstrap Flow

When Upwork/Cloudflare blocks the raw API login flow, use Playwright for initial auth bootstrap:

- `UPWORK_AUTH_STRATEGY=playwright`
- `UPWORK_PLAYWRIGHT_HEADLESS=false` (recommended for manual challenge/login)
- `UPWORK_PLAYWRIGHT_TIMEOUT_SECONDS=300`
- Optional: `UPWORK_PLAYWRIGHT_STORAGE_STATE_FILE=./playwright-state.json`

Behavior:

- Upworker opens Upwork in Chromium and listens for `/api/graphql/v1` responses.
- After the first successful GraphQL response, Upworker captures:
  - `Authorization` bearer token
  - relevant request headers (`cookie` and `x-*`)
- It stores the token in Redis (`UPWORK_TOKEN_REDIS_KEY`) and uses captured headers for
  subsequent GraphQL calls. Captured headers are cached in Redis as
  `UPWORK_GRAPHQL_HEADERS_REDIS_KEY`.
- If `UPWORK_PLAYWRIGHT_STORAGE_STATE_FILE` is set, browser session state is saved and reused.

`UPWORK_AUTH_STRATEGY` values:

- `api` (default): existing API login flow with `LOGIN_DATA`.
- `playwright`: browser bootstrap only.
- `auto`: try Playwright bootstrap first, then fallback to API login.

### Permissions / "oAuth2 client does not have permission"

If Upwork responds with a GraphQL error like:

- `Requested oAuth2 client does not have permission to see some of the requested fields`

then your `UPWORK_BEARER_TOKEN` (or your request headers) are not the same as what the Upwork
web app uses.

Practical fix:

- Capture the `Authorization: Bearer ...` header from your browser's job search GraphQL request.
- If the browser request also includes cookies or extra headers (ex: `x-oauth2-client-id`),
  copy them into `GRAPHQL_HEADERS` (yes, you can include a `cookie` header there if needed).

Environment variables:

- `GRAPHQL_HEADERS`: JSON dict of additional headers to send to GraphQL (optional).
- `UPWORK_COOKIE_HEADER`: raw Cookie header string to send with GraphQL requests.
- `UPWORK_COOKIE_FILE`: path to a file containing only the Cookie header value.
- `UPWORK_API_TENANT_ID`: convenience value for `x-upwork-api-tenantid`.
- `UPWORK_COOKIE_REDIS_KEY`: Redis key for cookie overrides (default `upwork_cookie`).
- `UPWORK_API_TENANT_REDIS_KEY`: Redis key for tenant overrides (default `upwork_api_tenant_id`).
- `TELEGRAM_BOT_TOKEN`: Telegram bot token for alerts (optional).
- `TELEGRAM_CHAT_ID`: Telegram chat id for alerts (optional).

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
