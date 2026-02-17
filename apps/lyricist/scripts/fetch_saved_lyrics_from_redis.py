#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import http.client
import json
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from redis import Redis

INDEX_KEY = "index:ytmusic:saved"
STAT_KEY_PREFIX = "stat:ytmusic:"
DEFAULT_API_BASE = "https://lrclib.net/api"
_TS_RE = re.compile(r"\[(?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d{1,3})?\]")
_PAREN_RE = re.compile(r"\s*[\(\[\{].*?[\)\]\}]\s*")
_WS_RE = re.compile(r"\s+")
_SEP_ARTIST_RE = re.compile(r"\s*(?:,|&|/| x | feat\.? | ft\.? | featuring )\s*", flags=re.IGNORECASE)
_NOISE_SUFFIX_RE = re.compile(
    r"\b(?:live|version|remix|remastered|marschversion|soundtrack|official video)\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class Track:
    id: str
    title: str
    artist: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch LRCLIB lyrics for saved YT Music tracks in Redis")
    p.add_argument("--redis-url", default="redis://localhost:6379/0")
    p.add_argument("--api-base", default=DEFAULT_API_BASE)
    p.add_argument("--out", default="apps/lyricist/scripts/tmp/lrclib/saved-lyrics.jsonl")
    p.add_argument("--summary-out", default="apps/lyricist/scripts/tmp/lrclib/saved-lyrics.summary.json")
    p.add_argument("--limit", type=int, default=0, help="0 means all")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--timeout-sec", type=float, default=10.0)
    p.add_argument("--max-chars", type=int, default=16000)
    p.add_argument(
        "--only-not-found-from",
        default="",
        help="Optional JSONL file; when set, process only records where status==not_found from that file",
    )
    return p.parse_args()


def _decode(v: Any) -> str:
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", errors="replace")
    return str(v)


def _load_tracks(r: Redis, limit: int) -> list[Track]:
    stop = -1 if limit <= 0 else max(0, limit - 1)
    raw_ids = r.zrevrange(INDEX_KEY, 0, stop)
    ids = [_decode(x) for x in raw_ids if x]

    out: list[Track] = []
    for tid in ids:
        raw = r.get(f"{STAT_KEY_PREFIX}{tid}")
        if not raw:
            continue
        try:
            payload = json.loads(_decode(raw))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        title = payload.get("title")
        artist = payload.get("artist")
        if isinstance(title, str) and isinstance(artist, str) and title.strip() and artist.strip():
            out.append(Track(id=tid, title=title.strip(), artist=artist.strip()))
    return out


def _load_not_found_tracks(path: Path) -> list[Track]:
    out: list[Track] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("status") != "not_found":
            continue
        tid = row.get("trackId")
        title = row.get("title")
        artist = row.get("artist")
        if isinstance(tid, str) and isinstance(title, str) and isinstance(artist, str):
            out.append(Track(id=tid, title=title, artist=artist))
    return out


def _strip_timestamps(text: str) -> str:
    return _TS_RE.sub("", text)


def _pick_lyrics(row: dict[str, Any]) -> str | None:
    plain = row.get("plainLyrics")
    if isinstance(plain, str) and plain.strip():
        return plain.strip()
    synced = row.get("syncedLyrics")
    if isinstance(synced, str) and synced.strip():
        stripped = _strip_timestamps(synced).strip()
        if stripped:
            return stripped
    return None


def _get_json(url: str, timeout_sec: float) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "portfolio-lyricist-saved-lyrics-export/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _normalize_title(text: str) -> str:
    s = text.strip().strip("\"' ")
    s = _PAREN_RE.sub(" ", s)
    s = s.replace(" - ", " ")
    s = _NOISE_SUFFIX_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def _normalize_artist(text: str) -> str:
    s = text.strip().strip("\"' ")
    primary = _SEP_ARTIST_RE.split(s)[0].strip()
    primary = _WS_RE.sub(" ", primary)
    return primary


def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _score_row(track: Track, row: dict[str, Any]) -> float:
    row_title = str(row.get("trackName") or row.get("name") or "").strip()
    row_artist = str(row.get("artistName") or "").strip()
    if not row_title:
        return 0.0
    t1 = _normalize_title(track.title)
    a1 = _normalize_artist(track.artist)
    rt = _normalize_title(row_title)
    ra = _normalize_artist(row_artist)
    return (_sim(t1, rt) * 0.75) + (_sim(a1, ra) * 0.25)


def _extract_best_row(track: Track, data: Any) -> dict[str, Any] | None:
    rows: list[dict[str, Any]] = []
    if isinstance(data, dict):
        rows = [data]
    elif isinstance(data, list):
        rows = [x for x in data if isinstance(x, dict)]
    if not rows:
        return None
    best: dict[str, Any] | None = None
    best_score = -1.0
    for row in rows:
        if not _pick_lyrics(row):
            continue
        score = _score_row(track, row)
        if score > best_score:
            best = row
            best_score = score
    return best


def _fetch_lrclib(track: Track, api_base: str, timeout_sec: float, max_chars: int) -> dict[str, Any]:
    t_norm = _normalize_title(track.title)
    a_norm = _normalize_artist(track.artist)
    pairs = [
        (track.title, track.artist),
        (t_norm, track.artist),
        (t_norm, a_norm),
    ]
    seen: set[tuple[str, str]] = set()
    unique_pairs: list[tuple[str, str]] = []
    for t, a in pairs:
        k = (t.strip(), a.strip())
        if k in seen or not k[0]:
            continue
        seen.add(k)
        unique_pairs.append(k)

    endpoints: list[str] = []
    base = api_base.rstrip("/")
    for t, a in unique_pairs:
        endpoints.append(f"{base}/get?{urlencode({'artist_name': a, 'track_name': t})}")
        endpoints.append(f"{base}/search?{urlencode({'track_name': t, 'artist_name': a})}")
    endpoints.append(f"{base}/search?{urlencode({'q': f'{t_norm} {a_norm}'.strip()})}")
    endpoints.append(f"{base}/search?{urlencode({'q': t_norm})}")

    for url in endpoints:
        try:
            data = _get_json(url, timeout_sec)
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            http.client.RemoteDisconnected,
            ConnectionError,
        ):
            continue

        row = _extract_best_row(track, data)
        if not row:
            continue
        lyrics = _pick_lyrics(row)
        if not lyrics:
            continue
        if len(lyrics) > max_chars:
            lyrics = lyrics[:max_chars].rstrip() + "\n...[lyrics truncated]"
        return {
            "trackId": track.id,
            "title": track.title,
            "artist": track.artist,
            "lyrics": lyrics,
            "lyricsUrl": row.get("url") if isinstance(row.get("url"), str) else None,
            "lrclibId": row.get("id"),
            "status": "ok",
        }

    return {
        "trackId": track.id,
        "title": track.title,
        "artist": track.artist,
        "lyrics": None,
        "lyricsUrl": None,
        "lrclibId": None,
        "status": "not_found",
    }


def main() -> int:
    args = parse_args()
    out_path = Path(args.out)
    summary_path = Path(args.summary_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    if args.only_not_found_from.strip():
        tracks = _load_not_found_tracks(Path(args.only_not_found_from))
    else:
        redis = Redis.from_url(args.redis_url)
        tracks = _load_tracks(redis, args.limit)
    total = len(tracks)

    found = 0
    missing = 0
    written = 0
    started = int(time.time())

    with out_path.open("w", encoding="utf-8") as f:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            for idx, result in enumerate(
                pool.map(
                    lambda t: _fetch_lrclib(t, args.api_base, args.timeout_sec, args.max_chars),
                    tracks,
                ),
                start=1,
            ):
                result["fetchedAt"] = int(time.time())
                f.write(json.dumps(result, ensure_ascii=True) + "\n")
                written += 1
                if result["status"] == "ok":
                    found += 1
                else:
                    missing += 1
                if idx % 10 == 0 or idx == total:
                    print(f"progress {idx}/{total} found={found} missing={missing}")

    summary = {
        "startedAt": started,
        "finishedAt": int(time.time()),
        "redisUrl": args.redis_url,
        "indexKey": INDEX_KEY,
        "tracksLoaded": total,
        "written": written,
        "found": found,
        "missing": missing,
        "output": str(out_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
