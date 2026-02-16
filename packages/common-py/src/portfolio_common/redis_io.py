import json
import time
from typing import Any, Dict

import structlog
from environs import env
from redis import Redis

env.read_env(recurse=False)

logger = structlog.get_logger()

REDIS_URL = env.str("REDIS_URL")
EVENTS_STREAM = env.str("REDIS_EVENTS_STREAM", default="events")


def redis_client() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)


def write_metric(r: Redis, key: str, payload: Dict[str, Any]) -> None:
    r.set(key, json.dumps(payload))


def emit_event(r: Redis, event_type: str, payload: Dict[str, Any]) -> None:
    r.xadd(
        EVENTS_STREAM,
        {
            "type": event_type,
            "payload": json.dumps(payload),
            "ts": str(int(time.time())),
        },
        "*",
    )
