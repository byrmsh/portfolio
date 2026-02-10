from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from environs import env
from openai import OpenAI
from ytmusicapi import YTMusic

from portfolio_common import emit_event, logger, redis_client
from portfolio_schema import RedisKeys, SavedLyricNote, YtMusicAnalysis

env.read_env(recurse=False)


YTMUSIC_PLAYLIST_ID = env.str("YTMUSIC_PLAYLIST_ID", default="")
WEB_ORIGIN = env.str("WEB_ORIGIN", default="http://localhost:4321")
OPENAI_API_KEY = env.str("OPENAI_API_KEY", default="")
OPENAI_MODEL = env.str("OPENAI_MODEL", default="gpt-5")


CURSOR_KEY = RedisKeys.stat("ytmusic", "cursor")


@dataclass(frozen=True)
class Track:
    id: str
    title: str
    artist: str
    album: str | None
    album_art_url: str | None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_origin(origin: str) -> str:
    return origin[:-1] if origin.endswith("/") else origin


def _ytmusic_track_url(video_id: str) -> str:
    return f"https://music.youtube.com/watch?v={video_id}"


def _genius_search_url(title: str, artist: str) -> str:
    from urllib.parse import quote_plus

    q = quote_plus(f"{title} {artist}")
    return f"https://genius.com/search?q={q}"


def _read_cursor(r) -> dict[str, Any] | None:
    raw = r.get(CURSOR_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _write_cursor(r, playlist_id: str, last_seen_track_id: str) -> None:
    r.set(
        CURSOR_KEY,
        json.dumps(
            {
                "playlistId": playlist_id,
                "lastSeenTrackId": last_seen_track_id,
                "updatedAt": _iso_now(),
            }
        ),
    )


def _extract_track(t: dict[str, Any]) -> Track | None:
    video_id = t.get("videoId") or t.get("video_id")
    title = t.get("title")
    if not video_id or not title:
        return None

    artists = t.get("artists") or []
    artist = ""
    if isinstance(artists, list) and artists:
        a0 = artists[0]
        if isinstance(a0, dict):
            artist = str(a0.get("name") or "")
        else:
            artist = str(a0)
    artist = artist or "Unknown"

    album = None
    alb = t.get("album")
    if isinstance(alb, dict) and alb.get("name"):
        album = str(alb["name"])

    album_art_url = None
    thumbs = t.get("thumbnails") or []
    if isinstance(thumbs, list) and thumbs:
        # pick the largest thumbnail
        best = None
        for th in thumbs:
            if not isinstance(th, dict):
                continue
            url = th.get("url")
            if not url:
                continue
            w = th.get("width") or 0
            if best is None or w > best[0]:
                best = (w, str(url))
        if best:
            album_art_url = best[1]

    return Track(id=str(video_id), title=str(title), artist=artist, album=album, album_art_url=album_art_url)


def _analysis_json_schema() -> dict[str, Any]:
    # Keep this in sync with:
    # - packages/schema/src/dashboard.ts (ytmusicAnalysisSchema)
    # - packages/schema-py/src/portfolio_schema/dashboard.py (YtMusicAnalysis)
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string", "minLength": 1},
            "source": {"type": "string", "enum": ["ytmusic"]},
            "title": {"type": "string", "minLength": 1},
            "artist": {"type": "string", "minLength": 1},
            "album": {"type": "string"},
            "albumArtUrl": {"type": "string"},
            "trackUrl": {"type": "string"},
            "lyricsUrl": {"type": "string"},
            "background": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "tldr": {"type": "string", "minLength": 1},
                    "notes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "title": {"type": "string", "minLength": 1},
                                "body": {"type": "string", "minLength": 1},
                            },
                            "required": ["title", "body"],
                        },
                    },
                },
                "required": ["tldr", "notes"],
            },
            "vocabulary": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "term": {"type": "string", "minLength": 1},
                        "literal": {"type": "string", "minLength": 1},
                        "meaning": {"type": "string", "minLength": 1},
                        "cefr": {"type": "string"},
                        "usage": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["term", "literal", "meaning"],
                },
            },
            "updatedAt": {"type": "string", "minLength": 1},
        },
        "required": [
            "id",
            "source",
            "title",
            "artist",
            "background",
            "vocabulary",
            "updatedAt",
        ],
    }


def _generate_analysis(track: Track) -> YtMusicAnalysis:
    # Fallback that keeps the pipeline moving even without OpenAI configured.
    if not OPENAI_API_KEY:
        return YtMusicAnalysis(
            id=track.id,
            source="ytmusic",
            title=track.title,
            artist=track.artist,
            album=track.album,
            albumArtUrl=track.album_art_url,
            trackUrl=_ytmusic_track_url(track.id),
            lyricsUrl=_genius_search_url(track.title, track.artist),
            background={
                "tldr": f"A track by {track.artist}. (LLM analysis not configured.)",
                "notes": [],
            },
            vocabulary=[],
            updatedAt=_iso_now(),
        )

    client = OpenAI(api_key=OPENAI_API_KEY)

    instructions = (
        "You write compact, high-signal music notes for a public portfolio site.\n"
        "You MUST NOT quote lyrics or reproduce any lyric lines.\n"
        "Output must follow the provided JSON schema exactly.\n"
        "Vocabulary items should explain terms/phrases a German learner might encounter in songs generally.\n"
        "Do not include example sentences from the song; if you include usage notes, they must be original."
    )

    user_input = (
        "Generate background notes and vocabulary explanations for this track.\n"
        f"track_id: {track.id}\n"
        f"title: {track.title}\n"
        f"artist: {track.artist}\n"
        f"album: {track.album or ''}\n"
        "Return JSON only."
    )

    resp = client.responses.create(
        model=OPENAI_MODEL,
        instructions=instructions,
        input=user_input,
        store=False,
        text={
            "format": {
                "type": "json_schema",
                "name": "ytmusic_analysis",
                "strict": True,
                "schema": _analysis_json_schema(),
            }
        },
    )

    payload = json.loads(resp.output_text)
    # Ensure required enrichments even if model leaves them blank.
    payload.setdefault("id", track.id)
    payload.setdefault("source", "ytmusic")
    payload.setdefault("title", track.title)
    payload.setdefault("artist", track.artist)
    payload.setdefault("album", track.album)
    payload.setdefault("albumArtUrl", track.album_art_url)
    payload.setdefault("trackUrl", _ytmusic_track_url(track.id))
    payload.setdefault("lyricsUrl", _genius_search_url(track.title, track.artist))
    payload.setdefault("updatedAt", _iso_now())

    return YtMusicAnalysis.model_validate(payload)


def _process_track(r, playlist_id: str, track: Track) -> None:
    saved_at = _iso_now()
    web_origin = _normalize_origin(WEB_ORIGIN)

    note = SavedLyricNote(
        id=track.id,
        source="ytmusic",
        title=track.title,
        artist=track.artist,
        # Static hosting: use a query-param based route so we don't need Astro dynamic SSR.
        noteUrl=f"{web_origin}/lyrics/note?id={track.id}",
        albumArtUrl=track.album_art_url,
        savedAt=saved_at,
    )

    analysis = _generate_analysis(track)

    stat_key = RedisKeys.stat("ytmusic", track.id)
    analysis_key = RedisKeys.stat_field("ytmusic", track.id, "analysis")

    r.set(stat_key, note.model_dump_json())
    r.set(analysis_key, analysis.model_dump_json())

    # Keep an index so the API can find "latest" quickly.
    r.zadd(RedisKeys.INDEX_LYRICS_RECENT, {track.id: int(time.time())})

    emit_event(r, "ytmusic_saved_updated", {"trackId": track.id, "key": stat_key})
    _write_cursor(r, playlist_id, track.id)


def _list_playlist_tracks(playlist_id: str) -> list[Track]:
    # ytmusicapi supports multiple auth modes; we keep this worker auth-agnostic for now.
    ytm = YTMusic()
    pl = ytm.get_playlist(playlist_id, limit=100)
    tracks_raw = pl.get("tracks") or []
    tracks: list[Track] = []
    for t in tracks_raw:
        if not isinstance(t, dict):
            continue
        tr = _extract_track(t)
        if tr:
            tracks.append(tr)
    return tracks


def main() -> None:
    if not YTMUSIC_PLAYLIST_ID:
        logger.info("lyricist.no_playlist_configured")
        return

    r = redis_client()
    cursor = _read_cursor(r)
    last_seen = (cursor or {}).get("lastSeenTrackId")

    logger.info("lyricist.sync.start", playlist_id=YTMUSIC_PLAYLIST_ID, last_seen=last_seen)
    tracks = _list_playlist_tracks(YTMUSIC_PLAYLIST_ID)
    if not tracks:
        logger.info("lyricist.sync.empty", playlist_id=YTMUSIC_PLAYLIST_ID)
        return

    # YT Music playlists are typically returned newest-first. Process all new tracks until we hit last_seen.
    new_tracks: list[Track] = []
    for tr in tracks:
        if last_seen and tr.id == last_seen:
            break
        new_tracks.append(tr)

    if not new_tracks:
        logger.info("lyricist.sync.noop", playlist_id=YTMUSIC_PLAYLIST_ID)
        return

    logger.info("lyricist.sync.new_tracks", count=len(new_tracks))
    # Process oldest-first so "latest" points at the most recent at the end of the run.
    for tr in reversed(new_tracks):
        logger.info("lyricist.track.process", track_id=tr.id, title=tr.title, artist=tr.artist)
        _process_track(r, YTMUSIC_PLAYLIST_ID, tr)

    logger.info("lyricist.sync.done", processed=len(new_tracks))


if __name__ == "__main__":
    main()
