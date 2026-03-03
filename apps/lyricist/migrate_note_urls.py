from __future__ import annotations

import json

from environs import env

from portfolio_common import logger, redis_client
from portfolio_schema import RedisKeys, SavedLyricNote

env.read_env(recurse=False)

WEB_ORIGIN = env.str("WEB_ORIGIN", default="http://localhost:4321")


def _normalize_origin(origin: str) -> str:
    return origin[:-1] if origin.endswith("/") else origin


def main() -> None:
    r = redis_client()
    ids = r.zrevrange(RedisKeys.INDEX_LYRICS_RECENT, 0, -1)
    logger.info("lyricist.migrate_note_urls.start", count=len(ids))

    web_origin = _normalize_origin(WEB_ORIGIN)
    updated = 0
    for track_id in ids:
        key = RedisKeys.stat("ytmusic", track_id)
        raw = r.get(key)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
            note = SavedLyricNote.model_validate(payload)
        except Exception:
            continue

        new_url = f"{web_origin}/playlist/note?id={track_id}"
        if note.noteUrl == new_url:
            continue

        note = note.model_copy(update={"noteUrl": new_url})
        r.set(key, note.model_dump_json())
        updated += 1

    logger.info("lyricist.migrate_note_urls.done", updated=updated)


if __name__ == "__main__":
    main()
