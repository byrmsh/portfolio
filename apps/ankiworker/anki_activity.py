from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from environs import env

from portfolio_common import emit_event, logger, redis_client, write_metric
from schema import ActivityCell, ActivitySeries, RedisKeys

env.read_env(recurse=False)

ANKI_COLLECTION_PATH = env.str("ANKI_COLLECTION_PATH", default="")
ANKI_TIMEZONE = env.str("ANKI_TIMEZONE", default="UTC")
ANKI_ROLLOVER_HOUR = env.int("ANKI_ROLLOVER_HOUR", default=4)
ANKI_SYNC_DIR = env.str("ANKI_SYNC_DIR", default="/tmp/anki-sync")

# If ANKI_COLLECTION_PATH is not provided, we'll try to sync down a disposable local
# collection using the Anki Rust backend (the `anki` PyPI package).
ANKIWEB_EMAIL = env.str("ANKIWEB_EMAIL", default="")
ANKIWEB_PASSWORD = env.str("ANKIWEB_PASSWORD", default="")
ANKI_SYNC_ENDPOINT = env.str("ANKI_SYNC_ENDPOINT", default="")


def _date_range_7_days(today: date) -> tuple[date, date]:
    # For "last N days" UI we want data up through today.
    end = today
    start = end - timedelta(days=6)
    return start, end


def _to_ms(dt: datetime) -> int:
    # SQLite revlog.id is a millisecond unix timestamp.
    return int(dt.timestamp() * 1000)


def _count_to_level(*, count: int, max_count: int) -> int:
    if count <= 0:
        return 0
    if max_count <= 1:
        return 4

    # Map activity into 4 non-zero buckets based on max intensity in the window.
    t2 = max(1, math.ceil(max_count * 0.33))
    t3 = max(1, math.ceil(max_count * 0.66))
    if count >= max_count:
        return 4
    if count >= t3:
        return 3
    if count >= t2:
        return 2
    return 1


def _open_collection_db(path: Path) -> sqlite3.Connection:
    # Use read-only mode to avoid locking the DB if it's on a shared volume.
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _fetch_review_ids_ms(
    *, collection_path: Path, start_ms: int, end_ms_exclusive: int
) -> list[int]:
    with _open_collection_db(collection_path) as conn:
        conn.row_factory = None
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM revlog WHERE id >= ? AND id < ?",
            (start_ms, end_ms_exclusive),
        )
        rows = cur.fetchall()
    return [int(r[0]) for r in rows]


def _iter_review_ids_ms_desc(*, collection_path: Path, max_ms_exclusive: int):
    with _open_collection_db(collection_path) as conn:
        conn.row_factory = None
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM revlog WHERE id < ? ORDER BY id DESC",
            (max_ms_exclusive,),
        )
        while True:
            rows = cur.fetchmany(4096)
            if not rows:
                break
            for row in rows:
                yield int(row[0])


def _to_anki_day(*, review_id_ms: int, tz: ZoneInfo, rollover_hour: int) -> date:
    local_dt = datetime.fromtimestamp(review_id_ms / 1000, tz=UTC).astimezone(tz)
    return (local_dt - timedelta(hours=rollover_hour)).date()


def _streak_from_full_history(
    *, collection_path: Path, tz: ZoneInfo, rollover_hour: int, end_day: date
) -> int:
    end_inclusive_local = datetime.combine(
        end_day + timedelta(days=1),
        time(hour=rollover_hour),
        tzinfo=tz,
    ).astimezone(UTC)
    end_inclusive_ms = _to_ms(end_inclusive_local)

    streak = 0
    last_seen_day: date | None = None
    expected_day: date | None = None

    for review_id_ms in _iter_review_ids_ms_desc(
        collection_path=collection_path,
        max_ms_exclusive=end_inclusive_ms + 1,
    ):
        day = _to_anki_day(review_id_ms=review_id_ms, tz=tz, rollover_hour=rollover_hour)
        if day == last_seen_day:
            continue
        last_seen_day = day

        if expected_day is None:
            expected_day = day
            streak = 1
            expected_day -= timedelta(days=1)
            continue

        if day == expected_day:
            streak += 1
            expected_day -= timedelta(days=1)
            continue
        break

    return streak


def _build_series_from_collection(
    *, collection_path: Path, tz: ZoneInfo, start: date, end: date, rollover_hour: int
) -> ActivitySeries:
    start_dt = datetime.combine(start, time(hour=rollover_hour), tzinfo=tz).astimezone(UTC)
    end_exclusive_dt = datetime.combine(
        end + timedelta(days=1),
        time(hour=rollover_hour),
        tzinfo=tz,
    ).astimezone(UTC)
    start_ms = _to_ms(start_dt)
    end_ms_exclusive = _to_ms(end_exclusive_dt)

    ids_ms = _fetch_review_ids_ms(
        collection_path=collection_path,
        start_ms=start_ms,
        end_ms_exclusive=end_ms_exclusive,
    )

    counts: dict[date, int] = defaultdict(int)
    for review_id_ms in ids_ms:
        d = _to_anki_day(review_id_ms=review_id_ms, tz=tz, rollover_hour=rollover_hour)
        # Safety in case the DB has weird timestamps.
        if start <= d <= end:
            counts[d] += 1

    max_count = max(counts.values(), default=0)

    cells: list[ActivityCell] = []
    cur = start
    while cur <= end:
        c = int(counts.get(cur, 0))
        cells.append(
            ActivityCell(
                date=cur,
                count=c,
                level=_count_to_level(count=c, max_count=max_count),
            )
        )
        cur += timedelta(days=1)

    streak = _streak_from_full_history(
        collection_path=collection_path,
        tz=tz,
        rollover_hour=rollover_hour,
        end_day=end,
    )

    return ActivitySeries(
        source="anki",
        label="Anki",
        cells=cells,
        streak=streak,
        rollover_hour=rollover_hour,
        timezone=str(tz),
        updated_at=datetime.now(tz=UTC),
    )


def _sync_down_collection_from_ankiweb(*, sync_dir: Path) -> Path:
    """Sync collection from AnkiWeb into a local directory.

    We intentionally bias towards "download" when a full sync is required, because this
    collector is read-only and should never overwrite server state.
    """
    if not ANKIWEB_EMAIL or not ANKIWEB_PASSWORD:
        raise RuntimeError(
            "missing ANKIWEB_EMAIL/ANKIWEB_PASSWORD (set ANKI_COLLECTION_PATH instead)"
        )

    # Import lazily: this pulls in the Rust bridge shared lib.
    from anki import sync_pb2
    from anki.collection import Collection

    sync_dir.mkdir(parents=True, exist_ok=True)
    col_path = sync_dir / "collection.anki2"

    col = Collection(str(col_path))
    try:
        auth = col.sync_login(
            username=ANKIWEB_EMAIL,
            password=ANKIWEB_PASSWORD,
            endpoint=ANKI_SYNC_ENDPOINT or None,
        )
        out = col.sync_collection(auth=auth, sync_media=False)

        # AnkiWeb may tell us to switch to a numbered host (eg https://sync6.ankiweb.net/).
        # Ensure subsequent requests (including full download) use it.
        if out.new_endpoint:
            logger.info("ankiworker.anki.new_endpoint", endpoint=out.new_endpoint)
            auth.endpoint = out.new_endpoint

        if out.required in (
            sync_pb2.SyncCollectionResponse.FULL_SYNC,
            sync_pb2.SyncCollectionResponse.FULL_DOWNLOAD,
        ):
            logger.info("ankiworker.anki.full_download_required", required=int(out.required))
            col.close_for_full_sync()
            col._backend.full_upload_or_download(
                sync_pb2.FullUploadOrDownloadRequest(auth=auth, upload=False)
            )
        elif out.required == sync_pb2.SyncCollectionResponse.FULL_UPLOAD:
            # Safety rail: never upload in automation.
            raise RuntimeError(
                "AnkiWeb requested a full upload; refusing to avoid overwriting server data"
            )
    finally:
        col.close()

    return col_path


def main() -> None:
    tz = ZoneInfo(ANKI_TIMEZONE)
    rollover_hour = max(0, min(23, int(ANKI_ROLLOVER_HOUR)))
    today = (datetime.now(tz=tz) - timedelta(hours=rollover_hour)).date()
    start, end = _date_range_7_days(today)

    collection_path = Path(ANKI_COLLECTION_PATH).expanduser() if ANKI_COLLECTION_PATH else None
    if collection_path and collection_path.exists():
        logger.info(
            "ankiworker.anki.start",
            collection=str(collection_path),
            tz=ANKI_TIMEZONE,
            rollover_hour=rollover_hour,
            start=str(start),
            end=str(end),
        )
        series = _build_series_from_collection(
            collection_path=collection_path,
            tz=tz,
            start=start,
            end=end,
            rollover_hour=rollover_hour,
        )
    else:
        try:
            synced_path = _sync_down_collection_from_ankiweb(sync_dir=Path(ANKI_SYNC_DIR))
            logger.info(
                "ankiworker.anki.start",
                collection=str(synced_path),
                tz=ANKI_TIMEZONE,
                rollover_hour=rollover_hour,
                start=str(start),
                end=str(end),
                mode="ankiweb-sync",
            )
            series = _build_series_from_collection(
                collection_path=synced_path,
                tz=tz,
                start=start,
                end=end,
                rollover_hour=rollover_hour,
            )
        except Exception as exc:
            logger.warning(
                "ankiworker.anki.no_data_source",
                anki_collection_path=ANKI_COLLECTION_PATH or None,
                anki_sync_dir=ANKI_SYNC_DIR or None,
                has_ankiweb_email=bool(ANKIWEB_EMAIL),
                error=str(exc),
            )
            cells: list[ActivityCell] = []
            cur = start
            while cur <= end:
                cells.append(ActivityCell(date=cur, level=0, count=0))
                cur += timedelta(days=1)
            series = ActivitySeries(
                source="anki",
                label="Anki",
                cells=cells,
                streak=0,
                rollover_hour=rollover_hour,
                timezone=str(tz),
                updated_at=datetime.now(tz=UTC),
            )

    r = redis_client()
    key = RedisKeys.stat("anki", "default")
    logger.debug(
        "ankiworker.anki.series_before_dump",
        rollover_hour=series.rollover_hour,
        timezone=series.timezone,
    )
    payload = series.model_dump(mode="json", by_alias=True, exclude_none=True)
    logger.debug("ankiworker.anki.payload", payload_keys=list(payload.keys()))
    write_metric(r, key, payload)
    emit_event(r, "anki_activity_updated", {"key": key})
    logger.info(
        "ankiworker.anki.done",
        key=key,
        cells=len(series.cells),
        streak=series.streak,
    )


if __name__ == "__main__":
    main()
