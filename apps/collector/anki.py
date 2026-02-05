from __future__ import annotations

from environs import env

from _common import emit_event, logger, redis_client, write_metric

env.read_env(recurse=False)


# Placeholder for future AnkiWeb internal API implementation.

def main() -> None:
    logger.info("collector.anki.todo")
    r = redis_client()
    key = "metric:anki:streak"
    write_metric(r, key, {"status": "todo"})
    emit_event(r, "anki_streak_updated", {"key": key})


if __name__ == "__main__":
    main()
