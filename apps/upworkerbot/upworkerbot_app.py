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
HTTP_TOKEN = env.str("UPWORKERBOT_HTTP_TOKEN", default="").strip()

UPWORK_TOKEN_REDIS_KEY = env.str("UPWORK_TOKEN_REDIS_KEY", default="upwork_token")
UPWORK_COOKIE_REDIS_KEY = env.str("UPWORK_COOKIE_REDIS_KEY", default="upwork_cookie")
UPWORK_API_TENANT_REDIS_KEY = env.str("UPWORK_API_TENANT_REDIS_KEY", default="upwork_api_tenant_id")

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
    logger.warning("TELEGRAM_ALLOWED_CHAT_ID is not set; bot will accept commands from any chat_id")


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
        def _unauthorized(self) -> None:
            self.send_response(401)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":false,"error":"unauthorized"}')

        def _bad_request(self, msg: str) -> None:
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.end_headers()
            payload = json.dumps({"ok": False, "error": msg})[:2000].encode("utf-8")
            self.wfile.write(payload)

        def _json_ok(self, payload: dict[str, Any]) -> None:
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))

        def _ensure_http_allowed(self) -> bool:
            if not HTTP_TOKEN:
                return True
            hdr = (self.headers.get("authorization") or "").strip()
            if hdr.lower().startswith("bearer "):
                tok = hdr.split(None, 1)[1].strip()
                return tok == HTTP_TOKEN
            tok2 = (self.headers.get("x-upworkerbot-token") or "").strip()
            return tok2 == HTTP_TOKEN

        def do_GET(self):  # noqa: N802
            if self.path != "/health":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def do_POST(self):  # noqa: N802
            if self.path != "/upwork_set_all":
                self.send_response(404)
                self.end_headers()
                return

            if not self._ensure_http_allowed():
                return self._unauthorized()

            try:
                content_length = int(self.headers.get("content-length") or "0")
            except ValueError:
                content_length = 0
            if content_length <= 0 or content_length > 5_000_000:
                return self._bad_request("invalid content-length")

            body = self.rfile.read(content_length)
            try:
                obj = json.loads(body.decode("utf-8"))
            except Exception:
                return self._bad_request("invalid json")
            if not isinstance(obj, dict):
                return self._bad_request("json must be an object")

            parsed = parse_set_all_payload(obj)
            if not parsed:
                return self._bad_request("provide token/cookie/tenant fields")

            updated = apply_set_all(parsed)
            masked = {k: mask_secret(v) for k, v in updated.items()}
            return self._json_ok({"ok": True, "updated": masked})

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
        "/upwork_set_all token=<...> cookie=<...> tenant=<...>\n"
        "/upwork_set_token <bearer_token>\n"
        "/upwork_set_cookie <cookie_header_value>\n"
        "/upwork_set_tenant <tenant_id>\n"
        "/upwork_clear_token\n"
        "/upwork_clear_cookie\n"
        "/upwork_clear_tenant\n"
    )


def parse_set_all_arg(arg: str) -> dict[str, str]:
    arg = arg.strip()
    if not arg:
        return {}

    if arg.startswith("{"):
        obj = json.loads(arg)
        if not isinstance(obj, dict):
            return {}
        out: dict[str, str] = {}
        for k in ("token", "cookie", "tenant"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                out[k] = v.strip()
        return out

    out: dict[str, str] = {}
    for part in arg.split():
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip().lower()
        v = v.strip()
        if k in ("token", "cookie", "tenant") and v:
            out[k] = v
    return out


def parse_set_all_payload(obj: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k in ("token", "cookie", "tenant"):
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out


def apply_set_all(parsed: dict[str, str]) -> dict[str, str]:
    updated: dict[str, str] = {}
    if "token" in parsed:
        r.set(UPWORK_TOKEN_REDIS_KEY, parsed["token"])
        r.set(UPWORK_TOKEN_UPDATED_AT_REDIS_KEY, now_iso())
        updated["token"] = parsed["token"]
    if "cookie" in parsed:
        r.set(UPWORK_COOKIE_REDIS_KEY, parsed["cookie"])
        r.set(UPWORK_COOKIE_UPDATED_AT_REDIS_KEY, now_iso())
        updated["cookie"] = parsed["cookie"]
    if "tenant" in parsed:
        r.set(UPWORK_API_TENANT_REDIS_KEY, parsed["tenant"])
        r.set(UPWORK_TENANT_UPDATED_AT_REDIS_KEY, now_iso())
        updated["tenant"] = parsed["tenant"]
    return updated


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

    if cmd == "/upwork_set_all":
        parsed = parse_set_all_arg(arg)
        if not parsed:
            return (
                "Usage:\n"
                "/upwork_set_all token=<...> cookie=<...> tenant=<...>\n"
                "or\n"
                '/upwork_set_all {"token":"...","cookie":"...","tenant":"..."}\n'
            )
        updated = apply_set_all(parsed)
        out_lines = []
        for k in ("token", "cookie", "tenant"):
            if k in updated:
                out_lines.append(f"{k}: {mask_secret(updated[k])}")
        return "Updated:\n" + "\n".join(out_lines)

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
