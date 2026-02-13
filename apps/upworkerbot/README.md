# UpworkerBot

Telegram bot that stores Upwork auth material in Redis for `apps/upworker` to use.

## Commands

- `/upwork_status`
- `/upwork_set_all token=<...> cookie=<...> tenant=<...>` (or JSON payload)
- `/upwork_set_token <bearer_token>`
- `/upwork_set_cookie <cookie_header_value>`
- `/upwork_set_tenant <tenant_id>`
- `/upwork_clear_token`
- `/upwork_clear_cookie`
- `/upwork_clear_tenant`

## HTTP

The bot also exposes an HTTP endpoint (useful because DevTools cURLs often exceed Telegram message limits):

- `POST /upwork_set_all` with JSON body:
  - `{ "token": "...", "cookie": "...", "tenant": "..." }`

If `UPWORKERBOT_HTTP_TOKEN` is set, include either:

- `Authorization: Bearer <token>`
- or `X-Upworkerbot-Token: <token>`

The bot never echoes back full secrets; it only reports lengths/prefixes.

## Local Helper Script

If you have a DevTools "copy as cURL" request, use the repo script to extract token/cookie/tenant and put a single `kubectl exec ...` update command on your clipboard:

```bash
python scripts/refine-upwork-curl.py < /path/to/curl.txt
```

## Env

- `REDIS_URL` (required)
- `TELEGRAM_BOT_TOKEN` (required)
- `TELEGRAM_ALLOWED_CHAT_ID` (recommended; numeric chat id)

Redis keys (defaults match `upworker`):

- `UPWORK_TOKEN_REDIS_KEY` (default `upwork_token`)
- `UPWORK_COOKIE_REDIS_KEY` (default `upwork_cookie`)
- `UPWORK_API_TENANT_REDIS_KEY` (default `upwork_api_tenant_id`)

Optional:

- `TELEGRAM_POLL_SECONDS` (default `2`)
- `CURL_CFFI_IMPERSONATE` (default `chrome`)
- `PORT` (health server, default `3000`)
- `UPWORKERBOT_HTTP_TOKEN` (optional; if set, required for `POST /upwork_set_all`)
