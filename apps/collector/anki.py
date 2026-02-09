from __future__ import annotations

from datetime import UTC, datetime, timedelta

from environs import env

from _common import emit_event, logger, redis_client, write_metric
from schema import ActivityCell, ActivitySeries, RedisKeys

env.read_env(recurse=False)


# Placeholder for future AnkiWeb internal API implementation.

def main() -> None:
    logger.info("collector.anki.todo_activity_series")
    today = datetime.now(tz=UTC).date()
    # Mirror GitHub windowing: 16 weeks ending today (UTC).
    end = today
    start = end - timedelta(days=(16 * 7) - 1)

    cells: list[ActivityCell] = []
    cur = start
    while cur <= end:
        cells.append(ActivityCell(date=cur, level=0, count=0))
        cur += timedelta(days=1)

    series = ActivitySeries(
        source="anki",
        label="Anki",
        cells=cells,
        streak=None,
        updatedAt=datetime.now(tz=UTC),
    )

    r = redis_client()
    key = RedisKeys.stat("anki", "default")
    write_metric(r, key, series.model_dump(mode="json"))
    emit_event(r, "anki_activity_updated", {"key": key})


if __name__ == "__main__":
    main()
