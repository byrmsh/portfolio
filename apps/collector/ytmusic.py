from __future__ import annotations

from environs import env

from _common import emit_event, logger, redis_client, write_metric

env.read_env(recurse=False)

YTMUSIC_PLAYLIST_URL = env.str("YTMUSIC_PLAYLIST_URL", default="")


# Placeholder for yt-dlp based ingestion.

def main() -> None:
    logger.info("collector.ytmusic.todo", playlist=YTMUSIC_PLAYLIST_URL)
    r = redis_client()
    key = "metric:ytmusic:playlist"
    write_metric(r, key, {"status": "todo", "playlist": YTMUSIC_PLAYLIST_URL})
    emit_event(r, "ytmusic_playlist_updated", {"key": key})


if __name__ == "__main__":
    main()
