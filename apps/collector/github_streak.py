from __future__ import annotations

from typing import Any

import httpx
from environs import env

from _common import emit_event, logger, redis_client, write_metric

env.read_env(recurse=False)

GITHUB_USERNAME = env.str("GITHUB_USERNAME")


def fetch_contrib_svg(username: str) -> str:
    url = f"https://github.com/users/{username}/contributions"
    res = httpx.get(url, timeout=30)
    res.raise_for_status()
    return res.text


def build_payload(svg: str) -> dict[str, Any]:
    return {"svg": svg}


def main() -> None:
    logger.info("collector.github.start", username=GITHUB_USERNAME)
    svg = fetch_contrib_svg(GITHUB_USERNAME)
    payload = build_payload(svg)
    r = redis_client()
    key = f"metric:github:streak:{GITHUB_USERNAME}"
    write_metric(r, key, payload)
    emit_event(r, "github_streak_updated", {"key": key})
    logger.info("collector.github.done", key=key)


if __name__ == "__main__":
    main()
