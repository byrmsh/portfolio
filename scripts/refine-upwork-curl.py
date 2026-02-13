#!/usr/bin/env python3
"""
Parse a DevTools "Copy as cURL" request (Upwork GraphQL) and generate an update command.

Default output: a single `kubectl exec ...` command that sets Redis keys used by upworker/upworkerbot.

This avoids Telegram message splitting and Telegram's "/..." linkification inside cookie values.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class UpworkAuth:
    token: str = ""
    cookie: str = ""
    tenant: str = ""

    def is_empty(self) -> bool:
        return not (self.token or self.cookie or self.tenant)


def _normalize_bearer(token: str) -> str:
    token = token.strip()
    if not token:
        return ""
    if token.lower().startswith("bearer "):
        return token.split(None, 1)[1].strip()
    return token


def _sanitize_bash_dollar_quote_token(s: str) -> str:
    # bash $'...' typically comes through shlex as a token starting with '$'.
    s = s.strip()
    if s.startswith("$"):
        return s[1:]
    return s


def parse_devtools_curl(text: str) -> UpworkAuth:
    text = text.strip()
    if not text:
        return UpworkAuth()

    # "copy as cURL" often uses backslash-newline continuations.
    text = text.replace("\\\r\n", " ").replace("\\\n", " ")

    parts = shlex.split(text, posix=True)
    if not parts:
        return UpworkAuth()

    headers: dict[str, str] = {}
    cookie = ""

    i = 0
    while i < len(parts):
        p = parts[i]
        if p in ("-H", "--header"):
            if i + 1 >= len(parts):
                break
            hv = parts[i + 1]
            i += 2
            if ":" not in hv:
                continue
            k, v = hv.split(":", 1)
            k = k.strip().lower()
            v = v.strip()
            if k:
                headers[k] = v
            continue
        if p in ("-b", "--cookie"):
            if i + 1 >= len(parts):
                break
            cookie = _sanitize_bash_dollar_quote_token(parts[i + 1]).strip()
            i += 2
            continue
        if p in ("--data", "--data-raw", "--data-binary", "--data-ascii", "-d"):
            # ignore body
            i += 2
            continue
        i += 1

    token = _normalize_bearer(headers.get("authorization", ""))
    tenant = headers.get("x-upwork-api-tenantid", "").strip()
    cookie_hdr = headers.get("cookie", "").strip()
    if not cookie and cookie_hdr:
        cookie = cookie_hdr

    return UpworkAuth(token=token, cookie=cookie, tenant=tenant)


def shquote(s: str) -> str:
    return shlex.quote(s)


def build_kubectl_exec_cmd(
    auth: UpworkAuth,
    namespace: str,
    deploy: str,
    redis_key_token: str,
    redis_key_cookie: str,
    redis_key_tenant: str,
    stat_key_token_ts: str,
    stat_key_cookie_ts: str,
    stat_key_tenant_ts: str,
) -> str:
    # Runs inside the upworkerbot pod which already has REDIS_URL and python deps.
    py = (
        "import os,time\n"
        "from redis import Redis\n"
        "r=Redis.from_url(os.environ['REDIS_URL'],decode_responses=True)\n"
        "now=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())\n"
        "t=os.environ.get('UPWORK_TOKEN','')\n"
        "c=os.environ.get('UPWORK_COOKIE','')\n"
        "n=os.environ.get('UPWORK_TENANT','')\n"
        f"rk_t={json.dumps(redis_key_token)}\n"
        f"rk_c={json.dumps(redis_key_cookie)}\n"
        f"rk_n={json.dumps(redis_key_tenant)}\n"
        f"sk_t={json.dumps(stat_key_token_ts)}\n"
        f"sk_c={json.dumps(stat_key_cookie_ts)}\n"
        f"sk_n={json.dumps(stat_key_tenant_ts)}\n"
        "if t:\n"
        "  r.set(rk_t,t); r.set(sk_t,now)\n"
        "if c:\n"
        "  r.set(rk_c,c); r.set(sk_c,now)\n"
        "if n:\n"
        "  r.set(rk_n,n); r.set(sk_n,now)\n"
        "print('ok')\n"
    )

    cmd = (
        f"kubectl -n {shquote(namespace)} exec deploy/{shquote(deploy)} -- "
        f"env UPWORK_TOKEN={shquote(auth.token)} "
        f"UPWORK_COOKIE={shquote(auth.cookie)} "
        f"UPWORK_TENANT={shquote(auth.tenant)} "
        f"python -c {shquote(py)}"
    )
    return cmd


def build_http_cmd(auth: UpworkAuth, port: int, http_token: str) -> str:
    payload = {
        "token": auth.token,
        "cookie": auth.cookie,
        "tenant": auth.tenant,
    }
    headers = ["-H", "content-type: application/json"]
    if http_token.strip():
        headers += ["-H", f"authorization: bearer {http_token.strip()}"]
    return (
        "curl -sS -X POST "
        + shquote(f"http://127.0.0.1:{port}/upwork_set_all")
        + " "
        + " ".join(shquote(h) for h in headers)
        + " --data "
        + shquote(json.dumps(payload, separators=(",", ":")))
    )


def maybe_copy(text: str) -> bool:
    try:
        p = subprocess.run(["wl-copy"], input=text.encode("utf-8"), check=False)
        return p.returncode == 0
    except FileNotFoundError:
        return False


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--mode",
        choices=["kubectl-exec", "http"],
        default="kubectl-exec",
        help="Output command mode (default: kubectl-exec).",
    )
    ap.add_argument("-n", "--namespace", default="portfolio")
    ap.add_argument(
        "--deploy",
        default="upworker-bot-deployment",
        help="Deployment to exec into for kubectl-exec mode.",
    )
    ap.add_argument("--http-port", type=int, default=3000)
    ap.add_argument("--http-token", default="")
    ap.add_argument("--no-copy", action="store_true", help="Do not use wl-copy.")
    args = ap.parse_args(argv)

    curl_text = sys.stdin.read()
    auth = parse_devtools_curl(curl_text)
    if auth.is_empty():
        print("error: could not extract token/cookie/tenant from input", file=sys.stderr)
        return 2

    if args.mode == "http":
        out = build_http_cmd(auth, port=args.http_port, http_token=args.http_token)
    else:
        out = build_kubectl_exec_cmd(
            auth,
            namespace=args.namespace,
            deploy=args.deploy,
            redis_key_token="upwork_token",
            redis_key_cookie="upwork_cookie",
            redis_key_tenant="upwork_api_tenant_id",
            stat_key_token_ts="stat:upwork:token_updated_at",
            stat_key_cookie_ts="stat:upwork:cookie_updated_at",
            stat_key_tenant_ts="stat:upwork:tenant_updated_at",
        )

    print(out)
    if not args.no_copy:
        copied = maybe_copy(out)
        if copied:
            print("(copied to clipboard via wl-copy)", file=sys.stderr)
        else:
            print("(wl-copy not available; printed to stdout)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

