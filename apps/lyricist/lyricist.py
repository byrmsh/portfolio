from __future__ import annotations

import json
import random
import re
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from environs import env

# Load .env before importing shared modules that read env vars at import time
# (e.g. portfolio_common.redis_io expects REDIS_URL).
env.read_env(recurse=False)

from openai import OpenAI
from pydantic import ValidationError
from ytmusicapi import YTMusic

from portfolio_common import emit_event, logger, redis_client
from portfolio_schema import RedisKeys, SavedLyricNote, YtMusicAnalysis, YtMusicVocabularyItem


YTMUSIC_PLAYLIST_ID = env.str("YTMUSIC_PLAYLIST_ID", default="")
WEB_ORIGIN = env.str("WEB_ORIGIN", default="http://localhost:4321")
LYRICIST_DRY_RUN = env.bool("LYRICIST_DRY_RUN", default=False)
LYRICIST_IGNORE_CURSOR = env.bool("LYRICIST_IGNORE_CURSOR", default=False)

# Mode:
# - sync: ingest playlist and enqueue analysis jobs only
# - analyze: process pending queue only
# - all: run sync then analyze
LYRICIST_MODE = env.str("LYRICIST_MODE", default="all").strip().lower()

# Queue-driven analysis controls (free-tier friendly defaults).
LYRICIST_ANALYSIS_MAX_PER_RUN = max(0, env.int("LYRICIST_ANALYSIS_MAX_PER_RUN", default=3))
LYRICIST_ANALYSIS_MIN_INTERVAL_SECONDS = max(
    0.0, env.float("LYRICIST_ANALYSIS_MIN_INTERVAL_SECONDS", default=10.0)
)
LYRICIST_ANALYSIS_BACKOFF_BASE_SECONDS = max(
    1.0, env.float("LYRICIST_ANALYSIS_BACKOFF_BASE_SECONDS", default=60.0)
)
LYRICIST_ANALYSIS_BACKOFF_MAX_SECONDS = max(
    LYRICIST_ANALYSIS_BACKOFF_BASE_SECONDS,
    env.float("LYRICIST_ANALYSIS_BACKOFF_MAX_SECONDS", default=3600.0),
)
LYRICIST_ANALYSIS_MAX_ATTEMPTS = max(1, env.int("LYRICIST_ANALYSIS_MAX_ATTEMPTS", default=5))
LYRICIST_REQUEUE_ERROR_FALLBACK_SCAN_LIMIT = max(
    0, env.int("LYRICIST_REQUEUE_ERROR_FALLBACK_SCAN_LIMIT", default=300)
)

# LLM provider wiring:
# - gemini: native Gemini API (structured output via responseSchema + responseMimeType)
# - openai: OpenAI Responses API (json_schema + strict)
# - auto: prefer Gemini if configured; else OpenAI if configured; else none
# - none: disable LLM analysis entirely
LYRICIST_LLM_PROVIDER = env.str("LYRICIST_LLM_PROVIDER", default="auto")

GEMINI_API_KEY = env.str("GEMINI_API_KEY", default="")
GEMINI_MODEL = env.str("GEMINI_MODEL", default="gemini-1.5-flash")
GEMINI_API_BASE = env.str(
    "GEMINI_API_BASE", default="https://generativelanguage.googleapis.com/v1beta"
)
GEMINI_USE_SEARCH = env.bool("GEMINI_USE_SEARCH", default=False)
GEMINI_SEARCH_DYNAMIC_THRESHOLD = env.float("GEMINI_SEARCH_DYNAMIC_THRESHOLD", default=0.7)

OPENAI_API_KEY = env.str("OPENAI_API_KEY", default="")
OPENAI_MODEL = env.str("OPENAI_MODEL", default="gpt-5")
LRCLIB_API_BASE = env.str("LRCLIB_API_BASE", default="https://lrclib.net/api")
LYRICIST_LYRICS_MAX_CHARS = max(1000, env.int("LYRICIST_LYRICS_MAX_CHARS", default=12000))


CURSOR_KEY = RedisKeys.stat("ytmusic", "cursor")
PENDING_ZSET_KEY = getattr(RedisKeys, "INDEX_LYRICS_ANALYSIS_PENDING", "index:ytmusic:analysis:pending")

_VOCAB_REQUIRED_FIELDS = {"id", "term", "exampleDe", "literalEn", "meaningEn", "exampleEn"}


def _ensure_flashcard_schema() -> None:
    if _VOCAB_REQUIRED_FIELDS.issubset(set(YtMusicVocabularyItem.model_fields.keys())):
        return
    raise RuntimeError(
        "portfolio-schema in this virtualenv is outdated for flashcards. "
        "Run: UV_CACHE_DIR=/tmp/uv-cache uv sync --reinstall-package portfolio-schema"
    )


@dataclass(frozen=True)
class Track:
    id: str
    title: str
    artist: str
    album: str | None
    album_art_url: str | None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> int:
    return int(time.time())


def _normalize_origin(origin: str) -> str:
    return origin[:-1] if origin.endswith("/") else origin


def _ytmusic_track_url(video_id: str) -> str:
    return f"https://music.youtube.com/watch?v={video_id}"


def _slugify_genius_part(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text or "")
    ascii_text = folded.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "unknown"


def _genius_lyrics_url(title: str, artist: str) -> str:
    artist_slug = _slugify_genius_part(artist)
    title_slug = _slugify_genius_part(title)
    return f"https://genius.com/{artist_slug}-{title_slug}-lyrics"


def _is_lrclib_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        host = (urlparse(value).netloc or "").lower()
    except Exception:
        return False
    return host == "lrclib.net" or host.endswith(".lrclib.net")


def _strip_lrc_timestamps(text: str) -> str:
    return re.sub(r"\[(?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d{1,3})?\]", "", text)


def _compact_lyrics_for_prompt(text: str, max_chars: int) -> str:
    lines = [line.strip() for line in text.splitlines()]
    compact = "\n".join(line for line in lines if line)
    if len(compact) <= max_chars:
        return compact
    return f"{compact[:max_chars].rstrip()}\n...[lyrics truncated]"


def _pick_lrclib_lyrics(item: dict[str, Any]) -> str | None:
    plain = item.get("plainLyrics")
    if isinstance(plain, str) and plain.strip():
        return plain.strip()

    synced = item.get("syncedLyrics")
    if isinstance(synced, str) and synced.strip():
        stripped = _strip_lrc_timestamps(synced).strip()
        if stripped:
            return stripped
    return None


def _lrclib_get_json(path: str, params: dict[str, str]) -> tuple[Any, str]:
    base = LRCLIB_API_BASE.rstrip("/")
    url = f"{base}/{path}?{urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "portfolio-lyricist/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw), url


def _fetch_lrclib_lyrics(track: Track) -> tuple[str | None, str | None]:
    common_params = {
        "artist_name": track.artist,
        "track_name": track.title,
    }
    if track.album:
        common_params["album_name"] = track.album

    endpoints = (
        ("get", common_params),
        ("search", common_params),
    )

    for path, params in endpoints:
        try:
            data, request_url = _lrclib_get_json(path, params)
        except urllib.error.HTTPError as e:
            logger.warning(
                "lyricist.lrclib.http_error",
                path=path,
                status=getattr(e, "code", None),
                track_id=track.id,
            )
            continue
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
            logger.warning("lyricist.lrclib.error", path=path, track_id=track.id, error=str(e))
            continue

        rows: list[dict[str, Any]] = []
        if isinstance(data, dict):
            rows = [data]
        elif isinstance(data, list):
            rows = [x for x in data if isinstance(x, dict)]

        for row in rows:
            lyrics = _pick_lrclib_lyrics(row)
            if not lyrics:
                continue
            source_url = row.get("url") if isinstance(row.get("url"), str) else None
            return _compact_lyrics_for_prompt(lyrics, LYRICIST_LYRICS_MAX_CHARS), source_url

        logger.info("lyricist.lrclib.no_lyrics_in_response", path=path, track_id=track.id, url=request_url)

    return None, None


def _lyrics_prompt_context(lyrics_text: str | None, lyrics_url: str | None) -> str:
    if not lyrics_text:
        return (
            "No lyrics were returned by lrclib for this track. "
            "If needed, use search/web tools to verify terms, but still do not quote lyrics.\n"
        )

    source = lyrics_url or "https://lrclib.net/"
    return (
        "Use this provided lyrics text as the primary source for term selection.\n"
        f"lyrics_source_url: {source}\n"
        "lyrics_text_start\n"
        f"{lyrics_text}\n"
        "lyrics_text_end\n"
    )


def _analysis_attempts_key(track_id: str) -> str:
    return RedisKeys.stat_field("ytmusic", track_id, "analysis_attempts")


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

    return Track(
        id=str(video_id), title=str(title), artist=artist, album=album, album_art_url=album_art_url
    )


def _slug_token(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t)
    t = re.sub(r"-{2,}", "-", t).strip("-")
    return t or "term"


def _vocab_item_id(track_id: str, term: str, idx: int) -> str:
    return f"{track_id}:{_slug_token(term)}:{idx:02d}"


def _analysis_json_schema() -> dict[str, Any]:
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
                        "id": {"type": "string", "minLength": 1},
                        "term": {"type": "string", "minLength": 1},
                        "exampleDe": {"type": "string", "minLength": 1},
                        "literalEn": {"type": "string", "minLength": 1},
                        "meaningEn": {"type": "string", "minLength": 1},
                        "exampleEn": {"type": "string", "minLength": 1},
                        "memoryHint": {"type": "string"},
                        "cefr": {"type": "string"},
                        "usage": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "id",
                        "term",
                        "exampleDe",
                        "literalEn",
                        "meaningEn",
                        "exampleEn",
                    ],
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
                        "id": {"type": "string"},
                        "term": {"type": "string"},
                        "exampleDe": {"type": "string"},
                        "literalEn": {"type": "string"},
                        "meaningEn": {"type": "string"},
                        "exampleEn": {"type": "string"},
                        "memoryHint": {"type": "string"},
                        "cefr": {"type": "string"},
                        "usage": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "id",
                        "term",
                        "exampleDe",
                        "literalEn",
                        "meaningEn",
                        "exampleEn",
                    ],
                },
            },
            "updatedAt": {"type": "string"},
        },
        "required": ["id", "source", "title", "artist", "background", "vocabulary", "updatedAt"],
    }


def _analysis_fallback(track: Track, reason: str) -> YtMusicAnalysis:
    return YtMusicAnalysis(
        id=track.id,
        source="ytmusic",
        title=track.title,
        artist=track.artist,
        album=track.album,
        albumArtUrl=track.album_art_url,
        trackUrl=_ytmusic_track_url(track.id),
        lyricsUrl=_genius_lyrics_url(track.title, track.artist),
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


def _llm_instructions() -> str:
    return (
        "You create compact, high-signal German learning notes for a public portfolio app.\n"
        "\n"
        "Hard rules (must follow):\n"
        "- NEVER quote lyrics or reproduce lyric lines, even partial.\n"
        "- Vocabulary terms must appear verbatim in this exact track's lyrics.\n"
        "- Do not invent historical facts about artist or song. If unsure, keep it generic.\n"
        "- Output strict JSON only, no markdown and no commentary.\n"
        "\n"
        "Required shape:\n"
        "- background.tldr: 1-2 concise sentences.\n"
        "- background.notes: 3-5 notes, each with title and 2-4 sentences.\n"
        "- vocabulary: 8-12 items.\n"
        "\n"
        "For each vocabulary item (required unless explicitly marked optional):\n"
        "- id: stable item id string\n"
        "- term: German word or phrase from the lyrics\n"
        "- exampleDe: original German example sentence using the term (not a lyric quote)\n"
        "- literalEn: concise literal gloss in English\n"
        "- meaningEn: optional nuance in English (register, connotation, grammar hints), not a redundant dictionary restatement\n"
        "- exampleEn: faithful English translation of exampleDe\n"
        "- cefr: optional CEFR estimate\n"
        "- memoryHint: optional objective etymology/word-family/compound breakdown if useful\n"
        "\n"
        "Quality bar:\n"
        "- Prioritize harder/high-yield vocabulary (roughly CEFR B1-C2).\n"
        "- Avoid trivial A1/A2 words unless central to song meaning or idiomatically important.\n"
        "- Prefer idioms, compounds, figurative terms, and culturally loaded wording when present.\n"
        "- If the song has few advanced terms, include the best available non-trivial terms.\n"
        "- Avoid generic dictionary-like filler.\n"
        "- Do not use subjective mnemonic phrasing (e.g., 'sounds like', 'think of').\n"
        "- Keep explanations practical for memorization.\n"
        "- Ensure valid JSON and all required keys are present.\n"
    )


def _select_llm_provider() -> str:
    p = (LYRICIST_LLM_PROVIDER or "auto").strip().lower()
    if p in {"gemini", "openai", "none"}:
        return p
    if GEMINI_API_KEY:
        return "gemini"
    if OPENAI_API_KEY:
        return "openai"
    return "none"


def _strip_code_fences(s: str) -> str:
    t = s.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.endswith("```"):
            t = t[: -len("```")]
    return t.strip()


def _normalize_url_like(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return s
    m = re.match(r"^\[([^\]]*)\]\(([^)]*)\)$", s)
    if not m:
        return s
    label, href = m.group(1).strip(), m.group(2).strip()
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if label.startswith("http://") or label.startswith("https://"):
        # Some models return [https://example.com]() or wrap URL labels in google redirect links.
        if not href:
            return label
        parsed = urlparse(href)
        if parsed.netloc.endswith("google.com") and parsed.path == "/search":
            q = parse_qs(parsed.query).get("q", [])
            if q and q[0].strip() == label:
                return label
        return label
    return href or label


def _validation_error_summary(e: ValidationError) -> str:
    items: list[str] = []
    for it in e.errors():
        loc = ".".join(str(p) for p in (it.get("loc") or []))
        msg = str(it.get("msg") or "")
        items.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(items[:20])


def _normalize_analysis_payload(
    track: Track, payload: dict[str, Any], *, fallback_lyrics_url: str | None = None
) -> dict[str, Any]:
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

    album_art = _blank_to_none(_normalize_url_like(payload.get("albumArtUrl")))
    payload["albumArtUrl"] = album_art if album_art is not None else (track.album_art_url or None)

    track_url = _blank_to_none(_normalize_url_like(payload.get("trackUrl")))
    payload["trackUrl"] = track_url if track_url is not None else _ytmusic_track_url(track.id)

    lyrics_url = _blank_to_none(_normalize_url_like(payload.get("lyricsUrl")))
    fallback_lyrics = _blank_to_none(_normalize_url_like(fallback_lyrics_url))
    if isinstance(lyrics_url, str) and _is_lrclib_url(lyrics_url):
        lyrics_url = None
    if isinstance(fallback_lyrics, str) and _is_lrclib_url(fallback_lyrics):
        fallback_lyrics = None
    payload["lyricsUrl"] = (
        lyrics_url
        if lyrics_url is not None
        else (fallback_lyrics or _genius_lyrics_url(track.title, track.artist))
    )

    vocab_raw = payload.get("vocabulary")
    vocab: list[dict[str, Any]] = []
    if isinstance(vocab_raw, list):
        for idx, item in enumerate(vocab_raw, start=1):
            if not isinstance(item, dict):
                continue
            term = str(item.get("term") or "").strip()
            if not term:
                continue
            item["id"] = str(item.get("id") or _vocab_item_id(track.id, term, idx))
            if not isinstance(item.get("memoryHint"), str) or not str(item.get("memoryHint") or "").strip():
                item["memoryHint"] = None
            if not isinstance(item.get("cefr"), str) or not str(item.get("cefr") or "").strip():
                item["cefr"] = None
            usage = item.get("usage")
            if isinstance(usage, list):
                item["usage"] = [str(u).strip() for u in usage if str(u).strip()]
            else:
                item["usage"] = None
            vocab.append(item)
    payload["vocabulary"] = vocab

    payload["updatedAt"] = _iso_now()

    return payload


def _generate_analysis_openai(
    track: Track, *, lyrics_text: str | None, lyrics_url: str | None
) -> YtMusicAnalysis:
    if not OPENAI_API_KEY:
        return _analysis_fallback(track, "LLM analysis not configured.")

    client = OpenAI(api_key=OPENAI_API_KEY)

    instructions = _llm_instructions()

    user_input = (
        "Generate background notes and flashcard-ready vocabulary for this track.\n"
        f"track_id: {track.id}\n"
        f"title: {track.title}\n"
        f"artist: {track.artist}\n"
        f"album: {track.album or ''}\n"
        f"{_lyrics_prompt_context(lyrics_text, lyrics_url)}"
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
    payload = _normalize_analysis_payload(track, payload, fallback_lyrics_url=lyrics_url)
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
        if model.startswith("gemini-1.5"):
            body["tools"] = [
                {
                    "google_search_retrieval": {
                        "dynamic_retrieval_config": {
                            "mode": "MODE_DYNAMIC",
                            "dynamic_threshold": GEMINI_SEARCH_DYNAMIC_THRESHOLD,
                        }
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


def _generate_analysis_gemini(
    track: Track, *, lyrics_text: str | None, lyrics_url: str | None
) -> YtMusicAnalysis:
    if not GEMINI_API_KEY:
        return _analysis_fallback(track, "LLM analysis not configured.")

    instructions = _llm_instructions()

    schema_hint = (
        "Return JSON only with exactly these keys:\n"
        "- id (string)\n"
        '- source (string; use "ytmusic")\n'
        "- title (string)\n"
        "- artist (string)\n"
        "- album (string or empty)\n"
        "- albumArtUrl (string or empty)\n"
        "- trackUrl (string)\n"
        "- lyricsUrl (string)\n"
        "- background (object: { tldr: string, notes: [{ title: string, body: string }] })\n"
        "- vocabulary (array of objects with required fields:\n"
        "  { id: string, term: string, exampleDe: string, literalEn: string, meaningEn: string, exampleEn: string, cefr?: string, memoryHint?: string })\n"
        "- updatedAt (string)\n"
        "Do not add extra keys.\n"
        "Vocabulary quality requirements:\n"
        "- 8-12 items\n"
        "- terms must be in the track lyrics\n"
        "- examples must be original (not lyric quotes)\n"
        "- prioritize harder/high-yield terms (roughly CEFR B1-C2) over simple basics\n"
        "- avoid trivial A1/A2 unless central to song meaning\n"
        "- literalEn should be short and learner-facing\n"
        "- meaningEn should add non-redundant nuance only\n"
        "- memoryHint should be objective etymology/compound info, never 'sounds like' style\n"
    )

    base_user_input = (
        "Generate background notes and flashcard-ready vocabulary for this track.\n"
        f"track_id: {track.id}\n"
        f"title: {track.title}\n"
        f"artist: {track.artist}\n"
        f"album: {track.album or ''}\n"
        f"{_lyrics_prompt_context(lyrics_text, lyrics_url)}"
        f"{schema_hint}"
        "Return JSON only."
    )

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

        payload = _normalize_analysis_payload(track, payload, fallback_lyrics_url=lyrics_url)

        try:
            return YtMusicAnalysis.model_validate(payload)
        except ValidationError as e:
            last_err = e
            logger.warning(
                "lyricist.gemini.validation_error",
                attempt=attempt,
                error=_validation_error_summary(e),
            )
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
    lyrics_text, lyrics_url = _fetch_lrclib_lyrics(track)
    provider = _select_llm_provider()
    if provider == "gemini":
        return _generate_analysis_gemini(track, lyrics_text=lyrics_text, lyrics_url=lyrics_url)
    if provider == "openai":
        return _generate_analysis_openai(track, lyrics_text=lyrics_text, lyrics_url=lyrics_url)
    return _analysis_fallback(track, "LLM analysis not configured.")


def _list_playlist_tracks(playlist_id: str) -> list[Track]:
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


def _enqueue_for_analysis(r, track_id: str) -> None:
    # Only keep pending if analysis is missing or invalid.
    existing_analysis = r.get(RedisKeys.stat_field("ytmusic", track_id, "analysis"))
    if existing_analysis:
        try:
            payload = json.loads(
                existing_analysis.decode("utf-8")
                if isinstance(existing_analysis, (bytes, bytearray))
                else str(existing_analysis)
            )
            analysis = YtMusicAnalysis.model_validate(payload)
            if _is_error_fallback(analysis):
                r.zadd(PENDING_ZSET_KEY, {track_id: _now_ts()})
                return
            r.zrem(PENDING_ZSET_KEY, track_id)
            return
        except Exception:
            pass

    r.zadd(PENDING_ZSET_KEY, {track_id: _now_ts()})


def _upsert_saved_note_and_index(r, track: Track) -> None:
    saved_at = _iso_now()
    web_origin = _normalize_origin(WEB_ORIGIN)
    note = SavedLyricNote(
        id=track.id,
        source="ytmusic",
        title=track.title,
        artist=track.artist,
        noteUrl=f"{web_origin}/lyrics/note?id={track.id}",
        albumArtUrl=track.album_art_url,
        savedAt=saved_at,
    )

    stat_key = RedisKeys.stat("ytmusic", track.id)
    r.set(stat_key, note.model_dump_json())
    r.zadd(RedisKeys.INDEX_LYRICS_RECENT, {track.id: _now_ts()})
    _enqueue_for_analysis(r, track.id)
    emit_event(r, "ytmusic_saved_updated", {"trackId": track.id, "key": stat_key})


def _prune_removed_tracks(r, playlist_track_ids: set[str]) -> int:
    raw_ids = r.zrange(RedisKeys.INDEX_LYRICS_RECENT, 0, -1)
    if not raw_ids:
        return 0

    removed = 0
    for rid in raw_ids:
        track_id = rid.decode("utf-8") if isinstance(rid, (bytes, bytearray)) else str(rid)
        if not track_id or track_id in playlist_track_ids:
            continue

        r.delete(
            RedisKeys.stat("ytmusic", track_id),
            RedisKeys.stat_field("ytmusic", track_id, "analysis"),
            _analysis_attempts_key(track_id),
        )
        r.zrem(RedisKeys.INDEX_LYRICS_RECENT, track_id)
        r.zrem(PENDING_ZSET_KEY, track_id)
        removed += 1

    if removed > 0:
        logger.info("lyricist.sync.pruned_removed_tracks", count=removed)
    return removed


def _run_sync(r) -> int:
    if not YTMUSIC_PLAYLIST_ID:
        logger.info("lyricist.no_playlist_configured")
        return 0

    cursor = _read_cursor(r)
    last_seen = (cursor or {}).get("lastSeenTrackId")
    if LYRICIST_IGNORE_CURSOR and last_seen:
        logger.info(
            "lyricist.sync.ignore_cursor", playlist_id=YTMUSIC_PLAYLIST_ID, last_seen=last_seen
        )
        last_seen = None

    logger.info("lyricist.sync.start", playlist_id=YTMUSIC_PLAYLIST_ID, last_seen=last_seen)
    tracks = _list_playlist_tracks(YTMUSIC_PLAYLIST_ID)
    playlist_track_ids = {t.id for t in tracks}
    removed_count = _prune_removed_tracks(r, playlist_track_ids)
    if not tracks:
        logger.info("lyricist.sync.empty", playlist_id=YTMUSIC_PLAYLIST_ID)
        return 0

    new_tracks: list[Track] = []
    for tr in tracks:
        if last_seen and tr.id == last_seen:
            break
        new_tracks.append(tr)

    if not new_tracks:
        logger.info("lyricist.sync.noop", playlist_id=YTMUSIC_PLAYLIST_ID, removed=removed_count)
        return 0

    for tr in reversed(new_tracks):
        logger.info("lyricist.track.sync", track_id=tr.id, title=tr.title, artist=tr.artist)
        _upsert_saved_note_and_index(r, tr)
        _write_cursor(r, YTMUSIC_PLAYLIST_ID, tr.id)

    logger.info("lyricist.sync.done", processed=len(new_tracks), removed=removed_count)
    return len(new_tracks)


def _track_from_saved_note(r, track_id: str) -> Track | None:
    raw = r.get(RedisKeys.stat("ytmusic", track_id))
    if not raw:
        return None
    try:
        payload = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None

    title = payload.get("title")
    artist = payload.get("artist")
    album_art_url = payload.get("albumArtUrl")
    if not isinstance(title, str) or not isinstance(artist, str):
        return None
    return Track(
        id=track_id,
        title=title,
        artist=artist,
        album=None,
        album_art_url=album_art_url if isinstance(album_art_url, str) else None,
    )


def _read_due_pending_track_ids(r, limit: int) -> list[str]:
    if limit <= 0:
        return []
    now = _now_ts()
    raw_ids = r.zrangebyscore(PENDING_ZSET_KEY, min="-inf", max=now, start=0, num=limit)
    out: list[str] = []
    for rid in raw_ids:
        if isinstance(rid, (bytes, bytearray)):
            out.append(rid.decode("utf-8"))
        else:
            out.append(str(rid))
    return [x for x in out if x]


def _requeue_error_fallbacks(r) -> int:
    if LYRICIST_REQUEUE_ERROR_FALLBACK_SCAN_LIMIT <= 0:
        return 0

    raw_ids = r.zrevrange(RedisKeys.INDEX_LYRICS_RECENT, 0, LYRICIST_REQUEUE_ERROR_FALLBACK_SCAN_LIMIT - 1)
    if not raw_ids:
        return 0

    now = _now_ts()
    requeued = 0

    for rid in raw_ids:
        track_id = rid.decode("utf-8") if isinstance(rid, (bytes, bytearray)) else str(rid)
        if not track_id:
            continue
        if r.zscore(PENDING_ZSET_KEY, track_id) is not None:
            continue

        raw = r.get(RedisKeys.stat_field("ytmusic", track_id, "analysis"))
        if not raw:
            continue
        try:
            payload = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw))
            analysis = YtMusicAnalysis.model_validate(payload)
        except Exception:
            continue

        if _is_error_fallback(analysis):
            r.zadd(PENDING_ZSET_KEY, {track_id: now})
            requeued += 1

    if requeued > 0:
        logger.info("lyricist.analysis.requeued_error_fallbacks", count=requeued)
    return requeued


def _schedule_retry(r, track_id: str) -> None:
    attempts_key = _analysis_attempts_key(track_id)
    attempts = r.incr(attempts_key)

    if attempts >= LYRICIST_ANALYSIS_MAX_ATTEMPTS:
        logger.warning("lyricist.analysis.max_attempts", track_id=track_id, attempts=attempts)
        next_ts = _now_ts() + int(LYRICIST_ANALYSIS_BACKOFF_MAX_SECONDS)
    else:
        backoff = min(
            LYRICIST_ANALYSIS_BACKOFF_MAX_SECONDS,
            LYRICIST_ANALYSIS_BACKOFF_BASE_SECONDS * (2 ** max(0, attempts - 1)),
        )
        jitter = random.uniform(0, LYRICIST_ANALYSIS_BACKOFF_BASE_SECONDS)
        next_ts = _now_ts() + int(backoff + jitter)

    r.zadd(PENDING_ZSET_KEY, {track_id: next_ts})


def _mark_analysis_success(r, track_id: str, analysis: YtMusicAnalysis) -> None:
    analysis_key = RedisKeys.stat_field("ytmusic", track_id, "analysis")
    r.set(analysis_key, analysis.model_dump_json())
    r.zrem(PENDING_ZSET_KEY, track_id)
    r.delete(_analysis_attempts_key(track_id))


def _run_analyze(r) -> int:
    if LYRICIST_ANALYSIS_MAX_PER_RUN <= 0:
        logger.info("lyricist.analysis.disabled_by_limit")
        return 0

    _requeue_error_fallbacks(r)
    ids = _read_due_pending_track_ids(r, LYRICIST_ANALYSIS_MAX_PER_RUN)
    if not ids:
        logger.info("lyricist.analysis.no_due_pending")
        return 0

    processed = 0
    for idx, track_id in enumerate(ids, start=1):
        tr = _track_from_saved_note(r, track_id)
        if not tr:
            logger.warning("lyricist.analysis.missing_saved_note", track_id=track_id)
            _schedule_retry(r, track_id)
            continue

        logger.info("lyricist.analysis.start", track_id=tr.id, title=tr.title, artist=tr.artist)
        analysis = _generate_analysis(tr)
        if _is_error_fallback(analysis):
            logger.warning("lyricist.analysis.failed", track_id=track_id)
            _schedule_retry(r, track_id)
            continue

        _mark_analysis_success(r, track_id, analysis)
        processed += 1

        if idx < len(ids) and LYRICIST_ANALYSIS_MIN_INTERVAL_SECONDS > 0:
            time.sleep(LYRICIST_ANALYSIS_MIN_INTERVAL_SECONDS)

    logger.info("lyricist.analysis.done", processed=processed, attempted=len(ids))
    return processed


def _mode_enabled(mode: str, value: str) -> bool:
    return value == "all" or value == mode


def main() -> None:
    _ensure_flashcard_schema()
    mode = LYRICIST_MODE if LYRICIST_MODE in {"sync", "analyze", "all"} else "all"

    if LYRICIST_DRY_RUN:
        if not YTMUSIC_PLAYLIST_ID:
            logger.info("lyricist.no_playlist_configured")
            return
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

    if _mode_enabled("sync", mode):
        _run_sync(r)

    if _mode_enabled("analyze", mode):
        _run_analyze(r)


if __name__ == "__main__":
    main()
