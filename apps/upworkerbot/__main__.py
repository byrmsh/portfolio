import json
import logging
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any, Optional

import structlog
from curl_cffi import requests
from environs import env
from redis import Redis

env.read_env(recurse=False)

REDIS_URL = env.str("REDIS_URL")
TELEGRAM_BOT_TOKEN = env.str("TELEGRAM_BOT_TOKEN").strip()
TELEGRAM_ALLOWED_CHAT_ID_RAW = env.str("TELEGRAM_ALLOWED_CHAT_ID", default="").strip()
TELEGRAM_POLL_SECONDS = env.float("TELEGRAM_POLL_SECONDS", default=2.0)
CURL_CFFI_IMPERSONATE = env.str("CURL_CFFI_IMPERSONATE", default="chrome").strip()
PORT = env.int("PORT", default=3000)

UPWORK_TOKEN_REDIS_KEY = env.str("UPWORK_TOKEN_REDIS_KEY", default="upwork_token")
UPWORK_COOKIE_REDIS_KEY = env.str("UPWORK_COOKIE_REDIS_KEY", default="upwork_cookie")
UPWORK_API_TENANT_REDIS_KEY = env.str(
    "UPWORK_API_TENANT_REDIS_KEY", default="upwork_api_tenant_id"
)

UPWORK_TOKEN_UPDATED_AT_REDIS_KEY = env.str(
    "UPWORK_TOKEN_UPDATED_AT_REDIS_KEY", default="stat:upwork:token_updated_at"
)
UPWORK_COOKIE_UPDATED_AT_REDIS_KEY = env.str(
    "UPWORK_COOKIE_UPDATED_AT_REDIS_KEY", default="stat:upwork:cookie_updated_at"
)
UPWORK_TENANT_UPDATED_AT_REDIS_KEY = env.str(
    "UPWORK_TENANT_UPDATED_AT_REDIS_KEY", default="stat:upwork:tenant_updated_at"
)

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


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def as_int(s: str) -> Optional[int]:
    s = s.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


TELEGRAM_ALLOWED_CHAT_ID = as_int(TELEGRAM_ALLOWED_CHAT_ID_RAW)
if TELEGRAM_ALLOWED_CHAT_ID is None:
    logger.warning(
        "TELEGRAM_ALLOWED_CHAT_ID is not set; bot will accept commands from any chat_id"
    )


def tg_api(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    res = requests.post(
        url,
        json=payload,
        timeout=30,
        impersonate=CURL_CFFI_IMPERSONATE or None,
    )
    res.raise_for_status()
    out = res.json()
    assert isinstance(out, dict), "Unexpected Telegram response"
    return out


def tg_send(chat_id: int, text: str) -> None:
    tg_api(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
    )


def mask_secret(s: str) -> str:
    s = s.strip()
    if not s:
        return "(empty)"
    prefix = s[:10]
    return f"{prefix}… (len={len(s)})"


def health_server() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path != "/health":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b"{\"ok\":true}")

        def log_message(self, format, *args):  # noqa: A002
            return

    httpd = HTTPServer(("0.0.0.0", PORT), Handler)
    httpd.serve_forever()


def ensure_allowed(chat_id: int) -> bool:
    if TELEGRAM_ALLOWED_CHAT_ID is None:
        return True
    return chat_id == TELEGRAM_ALLOWED_CHAT_ID


def cmd_help() -> str:
    return (
        "Commands:\n"
        "/upwork_status\n"
        "/upwork_set_token <bearer_token>\n"
        "/upwork_set_cookie <cookie_header_value>\n"
        "/upwork_set_tenant <tenant_id>\n"
        "/upwork_clear_token\n"
        "/upwork_clear_cookie\n"
        "/upwork_clear_tenant\n"
    )


def handle_command(chat_id: int, text: str) -> str:
    parts = text.strip().split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/start", "/help"):
        return cmd_help()

    if cmd == "/upwork_status":
        token = r.get(UPWORK_TOKEN_REDIS_KEY) or ""
        cookie = r.get(UPWORK_COOKIE_REDIS_KEY) or ""
        tenant = r.get(UPWORK_API_TENANT_REDIS_KEY) or ""
        token_ts = r.get(UPWORK_TOKEN_UPDATED_AT_REDIS_KEY) or "(unknown)"
        cookie_ts = r.get(UPWORK_COOKIE_UPDATED_AT_REDIS_KEY) or "(unknown)"
        tenant_ts = r.get(UPWORK_TENANT_UPDATED_AT_REDIS_KEY) or "(unknown)"
        return (
            "Upwork auth status:\n"
            f"token: {mask_secret(str(token))} updated_at={token_ts}\n"
            f"cookie: {mask_secret(str(cookie))} updated_at={cookie_ts}\n"
            f"tenant: {mask_secret(str(tenant))} updated_at={tenant_ts}\n"
        )

    if cmd == "/upwork_set_token":
        if not arg:
            return "Usage: /upwork_set_token <bearer_token>"
        r.set(UPWORK_TOKEN_REDIS_KEY, arg)
        r.set(UPWORK_TOKEN_UPDATED_AT_REDIS_KEY, now_iso())
        return f"Set token: {mask_secret(arg)}"

    if cmd == "/upwork_set_cookie":
        if not arg:
            return "Usage: /upwork_set_cookie <cookie_header_value>"
        r.set(UPWORK_COOKIE_REDIS_KEY, arg)
        r.set(UPWORK_COOKIE_UPDATED_AT_REDIS_KEY, now_iso())
        return f"Set cookie: {mask_secret(arg)}"

    if cmd == "/upwork_set_tenant":
        if not arg:
            return "Usage: /upwork_set_tenant <tenant_id>"
        r.set(UPWORK_API_TENANT_REDIS_KEY, arg)
        r.set(UPWORK_TENANT_UPDATED_AT_REDIS_KEY, now_iso())
        return f"Set tenant: {mask_secret(arg)}"

    if cmd == "/upwork_clear_token":
        r.delete(UPWORK_TOKEN_REDIS_KEY)
        r.set(UPWORK_TOKEN_UPDATED_AT_REDIS_KEY, now_iso())
        return "Cleared token."

    if cmd == "/upwork_clear_cookie":
        r.delete(UPWORK_COOKIE_REDIS_KEY)
        r.set(UPWORK_COOKIE_UPDATED_AT_REDIS_KEY, now_iso())
        return "Cleared cookie."

    if cmd == "/upwork_clear_tenant":
        r.delete(UPWORK_API_TENANT_REDIS_KEY)
        r.set(UPWORK_TENANT_UPDATED_AT_REDIS_KEY, now_iso())
        return "Cleared tenant."

    return "Unknown command.\n\n" + cmd_help()


def main() -> None:
    Thread(target=health_server, daemon=True).start()
    logger.info("Starting Telegram polling loop", poll_seconds=TELEGRAM_POLL_SECONDS)

    offset: Optional[int] = None
    backoff = 1.0

    while True:
        try:
            payload: dict[str, Any] = {"timeout": 20}
            if offset is not None:
                payload["offset"] = offset
            out = tg_api("getUpdates", payload)
            if not out.get("ok"):
                raise RuntimeError(f"Telegram API not ok: {json.dumps(out)[:200]}")

            backoff = 1.0
            updates = out.get("result") or []
            if not isinstance(updates, list):
                updates = []

            for upd in updates:
                if not isinstance(upd, dict):
                    continue
                update_id = upd.get("update_id")
                if isinstance(update_id, int):
                    offset = update_id + 1

                msg = upd.get("message") or upd.get("edited_message")
                if not isinstance(msg, dict):
                    continue
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                if not isinstance(chat_id, int):
                    continue

                text = msg.get("text") or ""
                if not isinstance(text, str) or not text.strip():
                    continue

                if not ensure_allowed(chat_id):
                    logger.warning("Rejected message from unauthorized chat_id", chat_id=chat_id)
                    continue

                logger.info("Handling command", chat_id=chat_id, text=text.splitlines()[0][:80])
                try:
                    reply = handle_command(chat_id, text)
                except Exception as e:
                    logger.exception("Command handler failed", exc_info=e)
                    reply = "Command failed on server. Check logs."
                tg_send(chat_id, reply)

            time.sleep(max(0.1, float(TELEGRAM_POLL_SECONDS)))
        except Exception as e:
            logger.warning("Polling loop error", error=str(e))
            time.sleep(min(30.0, backoff))
            backoff = min(30.0, backoff * 2)


if __name__ == "__main__":
    main()

