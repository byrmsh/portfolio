from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from environs import env

# Load .env before importing shared modules that read env vars at import time
# (e.g. portfolio_common.redis_io expects REDIS_URL).
env.read_env(recurse=False)

from openai import OpenAI
from pydantic import ValidationError
from ytmusicapi import YTMusic

from portfolio_common import emit_event, logger, redis_client
from portfolio_schema import RedisKeys, SavedLyricNote, YtMusicAnalysis


YTMUSIC_PLAYLIST_ID = env.str("YTMUSIC_PLAYLIST_ID", default="")
WEB_ORIGIN = env.str("WEB_ORIGIN", default="http://localhost:4321")
LYRICIST_DRY_RUN = env.bool("LYRICIST_DRY_RUN", default=False)
LYRICIST_REGENERATE_ANALYSIS = env.bool("LYRICIST_REGENERATE_ANALYSIS", default=False)
LYRICIST_RETRY_FAILED_ANALYSIS = env.bool("LYRICIST_RETRY_FAILED_ANALYSIS", default=True)
LYRICIST_RETRY_FAILED_LIMIT = env.int("LYRICIST_RETRY_FAILED_LIMIT", default=3)
# Ignore the Redis cursor and rescan the playlist from newest->oldest (up to the playlist fetch limit).
# Useful when you want to force (re)processing existing tracks.
LYRICIST_IGNORE_CURSOR = env.bool("LYRICIST_IGNORE_CURSOR", default=False)

# LLM provider wiring:
# - gemini: native Gemini API (structured output via responseSchema + responseMimeType)
# - openai: OpenAI Responses API (json_schema + strict)
# - auto: prefer Gemini if configured; else OpenAI if configured; else none
# - none: disable LLM analysis entirely
LYRICIST_LLM_PROVIDER = env.str("LYRICIST_LLM_PROVIDER", default="auto")

GEMINI_API_KEY = env.str("GEMINI_API_KEY", default="")
GEMINI_MODEL = env.str("GEMINI_MODEL", default="gemini-1.5-flash")
GEMINI_API_BASE = env.str("GEMINI_API_BASE", default="https://generativelanguage.googleapis.com/v1beta")
GEMINI_USE_SEARCH = env.bool("GEMINI_USE_SEARCH", default=False)
GEMINI_SEARCH_DYNAMIC_THRESHOLD = env.float("GEMINI_SEARCH_DYNAMIC_THRESHOLD", default=0.7)

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


def _analysis_gemini_schema() -> dict[str, Any]:
    # Gemini's responseSchema support is more limited than full JSON Schema.
    # Use a conservative subset (no additionalProperties/minLength/enum).
    return {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "source": {"type": "string"},
            "title": {"type": "string"},
            "artist": {"type": "string"},
            "album": {"type": "string"},
            "albumArtUrl": {"type": "string"},
            "trackUrl": {"type": "string"},
            "lyricsUrl": {"type": "string"},
            "background": {
                "type": "object",
                "properties": {
                    "tldr": {"type": "string"},
                    "notes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "body": {"type": "string"},
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
                    "properties": {
                        "term": {"type": "string"},
                        "literal": {"type": "string"},
                        "meaning": {"type": "string"},
                        "cefr": {"type": "string"},
                        "usage": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["term", "literal", "meaning"],
                },
            },
            "updatedAt": {"type": "string"},
        },
        "required": ["id", "source", "title", "artist", "background", "vocabulary", "updatedAt"],
    }


def _analysis_fallback(track: Track, reason: str) -> YtMusicAnalysis:
    # Keep the pipeline moving even if the LLM is unavailable/misconfigured.
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
            "tldr": f"A track by {track.artist}. ({reason})",
            "notes": [],
        },
        vocabulary=[],
        updatedAt=_iso_now(),
    )


def _is_error_fallback(analysis: YtMusicAnalysis) -> bool:
    t = (analysis.background.tldr or "").lower()
    return "llm analysis failed:" in t or "llm output invalid:" in t


def _raw_analysis_is_error_fallback(raw: str | bytes | None) -> bool:
    if not raw:
        return False
    try:
        s = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
        payload = json.loads(s)
        bg = payload.get("background") if isinstance(payload, dict) else None
        tldr = (bg or {}).get("tldr") if isinstance(bg, dict) else None
        if not isinstance(tldr, str):
            return False
        t = tldr.lower()
        return "llm analysis failed:" in t or "llm output invalid:" in t
    except Exception:
        return False


def _llm_instructions() -> str:
    return (
        "You write compact, high-signal music notes for a public portfolio site.\n"
        "\n"
        "Hard rules:\n"
        "- You MUST NOT quote lyrics or reproduce any lyric lines (even partial lines).\n"
        "- Vocabulary terms MUST be words/phrases that appear verbatim in the lyrics for this exact track.\n"
        "  Do not invent idioms or 'related' phrases that are not in the lyrics.\n"
        "- Do not fabricate factual claims about the artist/song history. If unsure, keep it generic.\n"
        "- Output must be JSON only and must match the provided schema exactly (no markdown).\n"
        "\n"
        "Content goals:\n"
        "- background.tldr: 1-2 sentences, concrete and specific.\n"
        "- background.notes: 3-5 notes. Each note: title + 2-4 sentences.\n"
        "  Prefer: musical arrangement, cultural/historical context (only if confident), themes/imagery,\n"
        "  language/register, and why it is interesting.\n"
        "- vocabulary: 8-12 items. Avoid trivial A1 dictionary entries unless there is a non-obvious nuance.\n"
        "  At least 4 items must be multiword expressions or collocations (and must appear in the lyrics).\n"
        "  For each item:\n"
        "  - term: German word/phrase\n"
        "  - literal: literal gloss\n"
        "  - meaning: nuanced explanation (register, connotation, grammar quirks)\n"
        "  - usage: 2-4 short bullet strings with original usage notes (no lyric examples).\n"
        "    Include collocations, common complements, case/preposition, separable verb patterns,\n"
        "    or false friends as relevant.\n"
        "  - cefr: optional; omit if unsure.\n"
    )


def _select_llm_provider() -> str:
    p = (LYRICIST_LLM_PROVIDER or "auto").strip().lower()
    if p in {"gemini", "openai", "none"}:
        return p
    # auto
    if GEMINI_API_KEY:
        return "gemini"
    if OPENAI_API_KEY:
        return "openai"
    return "none"


def _strip_code_fences(s: str) -> str:
    t = s.strip()
    if t.startswith("```"):
        # Remove a single fenced block wrapper if present.
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.endswith("```"):
            t = t[: -len("```")]
    return t.strip()


def _validation_error_summary(e: ValidationError) -> str:
    # Compact, model-friendly error summary: loc + msg only.
    items: list[str] = []
    for it in e.errors():
        loc = ".".join(str(p) for p in (it.get("loc") or []))
        msg = str(it.get("msg") or "")
        items.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(items[:20])


def _normalize_analysis_payload(track: Track, payload: dict[str, Any]) -> dict[str, Any]:
    # Align with TS schema expectations:
    # - url fields must be valid URLs or null/undefined (never "")
    # - optional strings should be null/undefined (never "")
    def _blank_to_none(v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    payload["id"] = str(payload.get("id") or track.id)
    payload["source"] = "ytmusic"
    payload["title"] = str(payload.get("title") or track.title)
    payload["artist"] = str(payload.get("artist") or track.artist)

    album = _blank_to_none(payload.get("album"))
    payload["album"] = album if album is not None else (track.album or None)

    album_art = _blank_to_none(payload.get("albumArtUrl"))
    payload["albumArtUrl"] = album_art if album_art is not None else (track.album_art_url or None)

    track_url = _blank_to_none(payload.get("trackUrl"))
    payload["trackUrl"] = track_url if track_url is not None else _ytmusic_track_url(track.id)

    lyrics_url = _blank_to_none(payload.get("lyricsUrl"))
    payload["lyricsUrl"] = lyrics_url if lyrics_url is not None else _genius_search_url(track.title, track.artist)

    # Always stamp analysis generation time.
    payload["updatedAt"] = _iso_now()

    return payload


def _generate_analysis_openai(track: Track) -> YtMusicAnalysis:
    if not OPENAI_API_KEY:
        return _analysis_fallback(track, "LLM analysis not configured.")

    client = OpenAI(api_key=OPENAI_API_KEY)

    instructions = _llm_instructions()

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
    payload = _normalize_analysis_payload(track, payload)
    return YtMusicAnalysis.model_validate(payload)


def _gemini_generate_content(
    *,
    api_key: str,
    model: str,
    system: str,
    user: str,
    response_schema: dict[str, Any] | None,
    use_search: bool,
) -> dict[str, Any]:
    url = f"{GEMINI_API_BASE}/models/{model}:generateContent?key={api_key}"
    body: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
        },
    }
    if response_schema is not None:
        body["generationConfig"]["responseSchema"] = response_schema
    if use_search:
        # Prefer the newer google_search tool when available; fall back to legacy retrieval.
        if model.startswith("gemini-1.5"):
            body["tools"] = [
                {
                    "google_search_retrieval": {
                        "dynamic_retrieval_config": {"mode": "MODE_DYNAMIC", "dynamic_threshold": GEMINI_SEARCH_DYNAMIC_THRESHOLD}
                    }
                }
            ]
        else:
            body["tools"] = [{"google_search": {}}]

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw)


def _gemini_extract_text(resp: dict[str, Any]) -> str:
    candidates = resp.get("candidates") or []
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("gemini: missing candidates")
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    if not isinstance(parts, list) or not parts:
        raise ValueError("gemini: missing content parts")
    for p in parts:
        if isinstance(p, dict) and isinstance(p.get("text"), str) and p["text"].strip():
            return p["text"]
    raise ValueError("gemini: missing text part")


def _generate_analysis_gemini(track: Track) -> YtMusicAnalysis:
    if not GEMINI_API_KEY:
        return _analysis_fallback(track, "LLM analysis not configured.")

    instructions = _llm_instructions()

    schema_hint = (
        "Return JSON only with exactly these keys:\n"
        "- id (string)\n"
        "- source (string; use \"ytmusic\")\n"
        "- title (string)\n"
        "- artist (string)\n"
        "- album (string or empty)\n"
        "- albumArtUrl (string or empty)\n"
        "- trackUrl (string)\n"
        "- lyricsUrl (string)\n"
        "- background (object: { tldr: string, notes: [{ title: string, body: string }] })\n"
        "- vocabulary (array of objects: { term: string, literal: string, meaning: string, cefr?: string, usage?: string[] })\n"
        "- updatedAt (string)\n"
        "Do not invent additional top-level keys.\n"
        "Vocabulary requirements:\n"
        "- 8-12 items\n"
        "- at least 4 multiword expressions or collocations\n"
        "- each item should include 2-4 usage bullets\n"
        "- every vocabulary term MUST appear verbatim in the lyrics for this exact track\n"
    )

    base_user_input = (
        "Generate background notes and vocabulary explanations for this track.\n"
        f"track_id: {track.id}\n"
        f"title: {track.title}\n"
        f"artist: {track.artist}\n"
        f"album: {track.album or ''}\n"
        "If tools are available, first use web search to find the lyrics for this exact track.\n"
        "Do not quote lyrics. Use the lyrics only to choose vocabulary terms that actually appear.\n"
        f"{schema_hint}"
        "Return JSON only."
    )

    # Try schema mode first; if it errors, fall back to plain JSON. If validation fails, retry once with repair.
    last_err: Exception | None = None
    user_input = base_user_input
    schema_mode: dict[str, Any] | None = _analysis_gemini_schema()

    for attempt in range(1, 4):
        try:
            resp = _gemini_generate_content(
                api_key=GEMINI_API_KEY,
                model=GEMINI_MODEL,
                system=instructions,
                user=user_input,
                response_schema=schema_mode,
                use_search=GEMINI_USE_SEARCH,
            )
            text = _gemini_extract_text(resp)
            payload = json.loads(_strip_code_fences(text))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = (e.read() or b"").decode("utf-8", errors="replace")[:500]
            except Exception:
                body = ""
            last_err = e
            logger.warning(
                "lyricist.gemini.http_error",
                attempt=attempt,
                status=getattr(e, "code", None),
                body=body,
            )
            schema_mode = None
            continue
        except (urllib.error.URLError, json.JSONDecodeError, ValueError) as e:
            last_err = e
            logger.warning("lyricist.gemini.error", attempt=attempt, error=str(e))
            schema_mode = None
            continue

        payload = _normalize_analysis_payload(track, payload)

        try:
            return YtMusicAnalysis.model_validate(payload)
        except ValidationError as e:
            last_err = e
            logger.warning("lyricist.gemini.validation_error", attempt=attempt, error=_validation_error_summary(e))
            user_input = (
                f"{base_user_input}\n"
                "The previous JSON was invalid. Fix it.\n"
                f"Validation errors: {_validation_error_summary(e)}\n"
                "Return corrected JSON only."
            )
            schema_mode = None
            continue

    return _analysis_fallback(track, f"LLM analysis failed: {last_err}")


def _generate_analysis(track: Track) -> YtMusicAnalysis:
    provider = _select_llm_provider()
    if provider == "gemini":
        return _generate_analysis_gemini(track)
    if provider == "openai":
        return _generate_analysis_openai(track)
    return _analysis_fallback(track, "LLM analysis not configured.")


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

    stat_key = RedisKeys.stat("ytmusic", track.id)
    analysis_key = RedisKeys.stat_field("ytmusic", track.id, "analysis")

    r.set(stat_key, note.model_dump_json())

    # Analysis can be expensive and depends on external APIs. Avoid regenerating on every touch unless asked.
    existing_analysis = r.get(analysis_key)
    if existing_analysis and not LYRICIST_REGENERATE_ANALYSIS and not _raw_analysis_is_error_fallback(existing_analysis):
        logger.info("lyricist.analysis.skip_existing", track_id=track.id)
    else:
        analysis = _generate_analysis(track)
        # If LLM call failed and we already had an analysis, don't overwrite good data with a fallback.
        if existing_analysis and _is_error_fallback(analysis):
            logger.warning("lyricist.analysis.keep_existing_on_error", track_id=track.id)
        else:
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


def _retry_failed_recent_analyses(r) -> None:
    if not LYRICIST_RETRY_FAILED_ANALYSIS:
        return
    limit = max(0, int(LYRICIST_RETRY_FAILED_LIMIT or 0))
    if limit <= 0:
        return

    ids = r.zrevrange(RedisKeys.INDEX_LYRICS_RECENT, 0, limit - 1)
    for raw_id in ids:
        track_id = raw_id.decode("utf-8") if isinstance(raw_id, (bytes, bytearray)) else str(raw_id)
        if not track_id:
            continue

        analysis_key = RedisKeys.stat_field("ytmusic", track_id, "analysis")
        existing = r.get(analysis_key)
        if existing and not _raw_analysis_is_error_fallback(existing):
            continue

        stat_key = RedisKeys.stat("ytmusic", track_id)
        note_raw = r.get(stat_key)
        if not note_raw:
            continue
        try:
            note = json.loads(note_raw.decode("utf-8") if isinstance(note_raw, (bytes, bytearray)) else str(note_raw))
        except Exception:
            continue
        if not isinstance(note, dict):
            continue
        title = note.get("title")
        artist = note.get("artist")
        album_art_url = note.get("albumArtUrl")
        if not isinstance(title, str) or not isinstance(artist, str):
            continue

        track = Track(
            id=track_id,
            title=title,
            artist=artist,
            album=None,
            album_art_url=album_art_url if isinstance(album_art_url, str) else None,
        )

        logger.info("lyricist.analysis.retry", track_id=track_id)
        analysis = _generate_analysis(track)
        if existing and _is_error_fallback(analysis):
            logger.warning("lyricist.analysis.retry_failed", track_id=track_id)
            continue
        r.set(analysis_key, analysis.model_dump_json())


def main() -> None:
    if not YTMUSIC_PLAYLIST_ID:
        logger.info("lyricist.no_playlist_configured")
        return

    if LYRICIST_DRY_RUN:
        tracks = _list_playlist_tracks(YTMUSIC_PLAYLIST_ID)
        if not tracks:
            logger.info("lyricist.sync.empty", playlist_id=YTMUSIC_PLAYLIST_ID)
            return
        tr = tracks[0]
        logger.info("lyricist.dry_run.track", track_id=tr.id, title=tr.title, artist=tr.artist)
        analysis = _generate_analysis(tr)
        print(analysis.model_dump_json())
        return

    r = redis_client()
    cursor = _read_cursor(r)
    last_seen = (cursor or {}).get("lastSeenTrackId")
    if LYRICIST_IGNORE_CURSOR and last_seen:
        logger.info("lyricist.sync.ignore_cursor", playlist_id=YTMUSIC_PLAYLIST_ID, last_seen=last_seen)
        last_seen = None

    logger.info("lyricist.sync.start", playlist_id=YTMUSIC_PLAYLIST_ID, last_seen=last_seen)
    tracks = _list_playlist_tracks(YTMUSIC_PLAYLIST_ID)
    if not tracks:
        logger.info("lyricist.sync.empty", playlist_id=YTMUSIC_PLAYLIST_ID)
        _retry_failed_recent_analyses(r)
        return

    # YT Music playlists are typically returned newest-first. Process all new tracks until we hit last_seen.
    new_tracks: list[Track] = []
    for tr in tracks:
        if last_seen and tr.id == last_seen:
            break
        new_tracks.append(tr)

    if not new_tracks:
        logger.info("lyricist.sync.noop", playlist_id=YTMUSIC_PLAYLIST_ID)
        _retry_failed_recent_analyses(r)
        return

    logger.info("lyricist.sync.new_tracks", count=len(new_tracks))
    # Process oldest-first so "latest" points at the most recent at the end of the run.
    for tr in reversed(new_tracks):
        logger.info("lyricist.track.process", track_id=tr.id, title=tr.title, artist=tr.artist)
        _process_track(r, YTMUSIC_PLAYLIST_ID, tr)

    _retry_failed_recent_analyses(r)
    logger.info("lyricist.sync.done", processed=len(new_tracks))


if __name__ == "__main__":
    main()
