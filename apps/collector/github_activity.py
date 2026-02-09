from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

import httpx
from environs import env

from _common import emit_event, logger, redis_client, write_metric
from schema import ActivityCell, ActivitySeries, RedisKeys

env.read_env(recurse=False)

GITHUB_USERNAME = env.str("GITHUB_USERNAME")
GITHUB_TOKEN = env.str("GITHUB_TOKEN")

ContributionLevel = Literal[
    "NONE",
    "FIRST_QUARTILE",
    "SECOND_QUARTILE",
    "THIRD_QUARTILE",
    "FOURTH_QUARTILE",
]


def _date_range_16_weeks(today: date) -> tuple[date, date]:
    # For "last N days" UI we want data up through today (UTC), not end-of-week.
    end = today
    start = end - timedelta(days=(16 * 7) - 1)
    return start, end


def _level_to_int(level: ContributionLevel) -> int:
    return {
        "NONE": 0,
        "FIRST_QUARTILE": 1,
        "SECOND_QUARTILE": 2,
        "THIRD_QUARTILE": 3,
        "FOURTH_QUARTILE": 4,
    }[level]


def fetch_contrib_calendar(
    *,
    username: str,
    token: str,
    start: date,
    end: date,
) -> dict[str, Any]:
    query = """
      query($login: String!, $from: DateTime!, $to: DateTime!) {
        user(login: $login) {
          contributionsCollection(from: $from, to: $to) {
            contributionCalendar {
              weeks {
                contributionDays {
                  date
                  contributionCount
                  contributionLevel
                }
              }
            }
          }
        }
      }
    """

    # Use full-day bounds in UTC for consistent results.
    from_dt = datetime.combine(start, time.min, tzinfo=UTC).isoformat()
    to_dt = datetime.combine(end, time.max, tzinfo=UTC).isoformat()

    res = httpx.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": {"login": username, "from": from_dt, "to": to_dt}},
        headers={
            "Authorization": f"bearer {token}",
            "User-Agent": "portfolio-collector",
        },
        timeout=30,
    )
    res.raise_for_status()
    payload = res.json()
    if payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL errors: {payload['errors']}")
    return payload


def build_series_from_payload(payload: dict[str, Any], *, start: date, end: date) -> ActivitySeries:
    weeks = (
        payload.get("data", {})
        .get("user", {})
        .get("contributionsCollection", {})
        .get("contributionCalendar", {})
        .get("weeks", [])
    )

    by_date: dict[date, tuple[int, int]] = {}
    for week in weeks:
        for day in week.get("contributionDays", []):
            d = date.fromisoformat(day["date"])
            lvl = _level_to_int(day["contributionLevel"])
            cnt = int(day["contributionCount"])
            by_date[d] = (lvl, cnt)

    cells: list[ActivityCell] = []
    cur = start
    while cur <= end:
        lvl, cnt = by_date.get(cur, (0, 0))
        cells.append(ActivityCell(date=cur, level=lvl, count=cnt))
        cur += timedelta(days=1)

    return ActivitySeries(
        source="github",
        label="GitHub",
        cells=cells,
        updatedAt=datetime.now(tz=UTC),
    )


def main() -> None:
    today = datetime.now(tz=UTC).date()
    start, end = _date_range_16_weeks(today)

    logger.info(
        "collector.github.start",
        username=GITHUB_USERNAME,
        start=str(start),
        end=str(end),
    )

    payload = fetch_contrib_calendar(
        username=GITHUB_USERNAME,
        token=GITHUB_TOKEN,
        start=start,
        end=end,
    )
    series = build_series_from_payload(payload, start=start, end=end)

    r = redis_client()
    key = RedisKeys.stat("github", "default")
    write_metric(r, key, series.model_dump(mode="json"))
    emit_event(r, "github_activity_updated", {"key": key})

    logger.info("collector.github.done", key=key, cells=len(series.cells))


if __name__ == "__main__":
    main()
