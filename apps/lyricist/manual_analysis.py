from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from environs import env
from pydantic import ValidationError

# Load .env before importing shared modules that read env vars at import time.
env.read_env(recurse=False)

from portfolio_common import redis_client
from portfolio_schema import RedisKeys, YtMusicAnalysis, YtMusicVocabularyItem


BATCH_DIR_DEFAULT = "tmp/lyricist-batches"
PENDING_ZSET_KEY = getattr(RedisKeys, "INDEX_LYRICS_ANALYSIS_PENDING", "index:ytmusic:analysis:pending")
LRCLIB_API_BASE = env.str("LRCLIB_API_BASE", default="https://lrclib.net/api")
LYRICIST_LYRICS_MAX_CHARS = max(1000, env.int("LYRICIST_LYRICS_MAX_CHARS", default=12000))
LYRICIST_LRCLIB_TIMEOUT_SEC = max(2, env.int("LYRICIST_LRCLIB_TIMEOUT_SEC", default=6))
LYRICIST_LRCLIB_MAX_WORKERS = max(1, env.int("LYRICIST_LRCLIB_MAX_WORKERS", default=4))
_MD_LINK_RE = re.compile(r"^\[([^\]]*)\]\(([^)]*)\)$")

_VOCAB_REQUIRED_FIELDS = {"id", "term", "exampleDe", "literalEn", "meaningEn", "exampleEn"}


def _ensure_flashcard_schema() -> None:
    if _VOCAB_REQUIRED_FIELDS.issubset(set(YtMusicVocabularyItem.model_fields.keys())):
        return
    raise RuntimeError(
        "portfolio-schema in this virtualenv is outdated for flashcards. "
        "Run: UV_CACHE_DIR=/tmp/uv-cache uv sync --reinstall-package portfolio-schema"
    )


@dataclass(frozen=True)
class TrackSeed:
    id: str
    title: str
    artist: str
    albumArtUrl: str | None
    trackUrl: str | None


def _decode(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8")
    return str(value)


def _normalize_url_like(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return s
    m = _MD_LINK_RE.match(s)
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


def _normalize_import_payload(item: dict[str, Any]) -> dict[str, Any]:
    out = dict(item)
    for key in ("albumArtUrl", "trackUrl", "lyricsUrl"):
        out[key] = _normalize_url_like(out.get(key))
    return out


def _load_saved_track(r, track_id: str) -> TrackSeed | None:
    raw = r.get(RedisKeys.stat("ytmusic", track_id))
    if not raw:
        return None
    try:
        payload = json.loads(_decode(raw))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None

    title = payload.get("title")
    artist = payload.get("artist")
    if not isinstance(title, str) or not isinstance(artist, str):
        return None

    return TrackSeed(
        id=track_id,
        title=title,
        artist=artist,
        albumArtUrl=payload.get("albumArtUrl") if isinstance(payload.get("albumArtUrl"), str) else None,
        trackUrl=f"https://music.youtube.com/watch?v={track_id}",
    )


def _analysis_exists_and_valid(r, track_id: str) -> bool:
    raw = r.get(RedisKeys.stat_field("ytmusic", track_id, "analysis"))
    if not raw:
        return False
    try:
        payload = json.loads(_decode(raw))
        YtMusicAnalysis.model_validate(payload)
        return True
    except Exception:
        return False


def _collect_batch_ids(r, source: str, batch_size: int, offset: int) -> list[str]:
    if source == "pending":
        ids = r.zrange(PENDING_ZSET_KEY, offset, offset + batch_size - 1)
        return [_decode(x) for x in ids]

    # source == missing
    ids = r.zrevrange(RedisKeys.INDEX_LYRICS_RECENT, 0, -1)
    out: list[str] = []
    for raw in ids:
        track_id = _decode(raw)
        if not track_id:
            continue
        if _analysis_exists_and_valid(r, track_id):
            continue
        out.append(track_id)
    return out[offset : offset + batch_size]


def _build_batch(tracks: list[TrackSeed]) -> dict[str, Any]:
    return {
        "tracks": [asdict(t) for t in tracks],
        "count": len(tracks),
    }


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


def _lrclib_get_json(path: str, params: dict[str, str]) -> Any:
    base = LRCLIB_API_BASE.rstrip("/")
    url = f"{base}/{path}?{urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "portfolio-lyricist-manual-analysis/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=LYRICIST_LRCLIB_TIMEOUT_SEC) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _fetch_lrclib_lyrics(track: TrackSeed) -> tuple[str | None, str | None]:
    params = {"artist_name": track.artist, "track_name": track.title}
    endpoints = ("get", "search")
    for path in endpoints:
        try:
            data = _lrclib_get_json(path, params)
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
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
            lyrics_url = row.get("url") if isinstance(row.get("url"), str) else None
            return _compact_lyrics_for_prompt(lyrics, LYRICIST_LYRICS_MAX_CHARS), lyrics_url

    return None, None


def _build_lyrics_block(t: TrackSeed) -> str:
    lyrics_text, lyrics_url = _fetch_lrclib_lyrics(t)
    source = lyrics_url or "https://lrclib.net/"
    if lyrics_text:
        return (
            f"- id: {t.id}\n"
            f"  title: {t.title}\n"
            f"  artist: {t.artist}\n"
            f"  lyrics_source_url: {source}\n"
            "  lyrics_text_start\n"
            f"{lyrics_text}\n"
            "  lyrics_text_end"
        )
    return (
        f"- id: {t.id}\n"
        f"  title: {t.title}\n"
        f"  artist: {t.artist}\n"
        "  lyrics_status: not_found_via_lrclib\n"
        "  hint: if needed, use search/web tools to verify terms; still do not quote lyrics"
    )


def _build_lyrics_context(tracks: list[TrackSeed]) -> str:
    workers = min(len(tracks), LYRICIST_LRCLIB_MAX_WORKERS)
    if workers <= 1:
        return "\n\n".join(_build_lyrics_block(t) for t in tracks)

    blocks: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for block in pool.map(_build_lyrics_block, tracks):
            blocks.append(block)
    return "\n\n".join(blocks)


def _build_prompt(tracks: list[TrackSeed]) -> str:
    tracks_json = json.dumps([asdict(t) for t in tracks], ensure_ascii=False, indent=2)
    lyrics_context = _build_lyrics_context(tracks)
    return (
        "You are generating strict JSON for flashcard-ready German vocabulary analysis.\n"
        "Use provided lyrics text (from lrclib) as the primary source for each track.\n"
        "Only if lyrics are missing for a track, use web/search tools to verify terms.\n"
        "Do not quote lyrics or partial lyric lines anywhere in the output.\n"
        "\n"
        "Return a JSON array. Each element must match this shape exactly:\n"
        "{\n"
        '  "id": string,\n'
        '  "source": "ytmusic",\n'
        '  "title": string,\n'
        '  "artist": string,\n'
        '  "album": string,\n'
        '  "albumArtUrl": string,\n'
        '  "trackUrl": string,\n'
        '  "lyricsUrl": string,\n'
        '  "background": {"tldr": string, "notes": [{"title": string, "body": string}]},\n'
        '  "vocabulary": [\n'
        "    {\n"
        '      "id": string,\n'
        '      "term": string,\n'
        '      "exampleDe": string,\n'
        '      "literalEn": string,\n'
        '      "meaningEn": string,\n'
        '      "exampleEn": string,\n'
        '      "cefr": string,\n'
        '      "memoryHint": string\n'
        "    }\n"
        "  ],\n"
        '  "updatedAt": string\n'
        "}\n"
        "\n"
        "Requirements:\n"
        "- 8-12 vocabulary items per track.\n"
        "- Vocabulary terms must appear in the song lyrics.\n"
        "- Prioritize harder/high-yield terms (roughly CEFR B1-C2).\n"
        "- Avoid trivial A1/A2 terms unless central to the song meaning.\n"
        "- exampleDe must be original and not a lyric quote.\n"
        "- exampleEn must translate exampleDe faithfully.\n"
        "- literalEn should be the primary learner-facing translation (short and direct).\n"
        "- meaningEn should only add non-redundant nuance (register/connotation/grammar) and stay concise.\n"
        "- memoryHint should be objective only: etymology, word-family, or compound breakdown.\n"
        "- Do not use subjective hints like 'sounds like' or 'think of'.\n"
        "- Output JSON only, no markdown wrappers.\n"
        "\n"
        "Tracks:\n"
        f"{tracks_json}\n"
        "\n"
        "Lyrics context by track:\n"
        f"{lyrics_context}\n"
    )


def _build_template(tracks: list[TrackSeed]) -> list[dict[str, Any]]:
    template: list[dict[str, Any]] = []
    for t in tracks:
        template.append(
            {
                "id": t.id,
                "source": "ytmusic",
                "title": t.title,
                "artist": t.artist,
                "album": "",
                "albumArtUrl": t.albumArtUrl or "",
                "trackUrl": t.trackUrl or "",
                "lyricsUrl": "",
                "background": {"tldr": "", "notes": [{"title": "", "body": ""}]},
                "vocabulary": [
                    {
                        "id": f"{t.id}:term:01",
                        "term": "",
                        "exampleDe": "",
                        "literalEn": "",
                        "meaningEn": "",
                        "exampleEn": "",
                        "cefr": "",
                        "memoryHint": "",
                    }
                ],
                "updatedAt": "",
            }
        )
    return template


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def cmd_prepare_batch(args: argparse.Namespace) -> int:
    _ensure_flashcard_schema()
    r = redis_client()
    if args.offset is None:
        offset = (max(args.batch_number, 1) - 1) * args.batch_size
    else:
        offset = args.offset

    ids = _collect_batch_ids(r, args.source, args.batch_size, offset)
    tracks: list[TrackSeed] = []
    for track_id in ids:
        tr = _load_saved_track(r, track_id)
        if tr:
            tracks.append(tr)

    if not tracks:
        if not args.quiet:
            print("No tracks found for this batch.", flush=True)
        # Allow wrapper scripts to detect "empty batch" without parsing output.
        return 3 if args.stdout_prompt else 0

    prompt = _build_prompt(tracks)
    if args.stdout_prompt:
        print(prompt, end="")

    if args.no_files:
        return 0

    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)
    batch_num = args.batch_number
    input_path = out_dir / f"batch-{batch_num:03d}.input.json"
    prompt_path = out_dir / f"batch-{batch_num:03d}.prompt.txt"
    template_path = out_dir / f"batch-{batch_num:03d}.response.template.json"

    input_path.write_text(json.dumps(_build_batch(tracks), ensure_ascii=False, indent=2) + "\n")
    prompt_path.write_text(prompt)
    template_path.write_text(json.dumps(_build_template(tracks), ensure_ascii=False, indent=2) + "\n")

    if not args.quiet:
        print(f"Wrote: {input_path}")
        print(f"Wrote: {prompt_path}")
        print(f"Wrote: {template_path}")
        print(f"Tracks in batch: {len(tracks)}")
    return 0


def cmd_import_batch(args: argparse.Namespace) -> int:
    _ensure_flashcard_schema()
    r = redis_client()
    path = Path(args.file)
    payload = json.loads(path.read_text())
    if not isinstance(payload, list):
        raise ValueError("Imported file must be a JSON array")

    imported = 0
    failed = 0

    for idx, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            failed += 1
            print(f"[{idx}] invalid item: expected object")
            if args.strict:
                return 1
            continue

        try:
            normalized_item = _normalize_import_payload(item)
            analysis = YtMusicAnalysis.model_validate(normalized_item)
        except ValidationError as e:
            failed += 1
            print(f"[{idx}] validation error: {e.errors()[0].get('msg', 'invalid analysis')}")
            if args.strict:
                return 1
            continue

        track_id = analysis.id
        if args.dry_run:
            imported += 1
            continue

        analysis_key = RedisKeys.stat_field("ytmusic", track_id, "analysis")
        r.set(analysis_key, analysis.model_dump_json())
        r.zrem(PENDING_ZSET_KEY, track_id)
        r.delete(RedisKeys.stat_field("ytmusic", track_id, "analysis_attempts"))
        imported += 1

    print(f"Imported: {imported}")
    print(f"Failed: {failed}")
    print(f"Mode: {'dry-run' if args.dry_run else 'write'}")
    return 0 if failed == 0 or not args.strict else 1


def cmd_batch_status(args: argparse.Namespace) -> int:
    _ensure_flashcard_schema()
    r = redis_client()
    pending = r.zcard(PENDING_ZSET_KEY)
    total_saved = r.zcard(RedisKeys.INDEX_LYRICS_RECENT)

    sample_ids = r.zrange(PENDING_ZSET_KEY, 0, max(0, args.peek - 1))
    sample = []
    for raw in sample_ids:
        track_id = _decode(raw)
        tr = _load_saved_track(r, track_id)
        sample.append(
            {
                "id": track_id,
                "title": tr.title if tr else None,
                "artist": tr.artist if tr else None,
            }
        )

    out = {
        "pending": pending,
        "saved": total_saved,
        "next": sample,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manual analysis batch workflow for lyricist")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser("prepare-batch", help="Export a batch and prompt from Redis")
    p_prepare.add_argument("--source", choices=["pending", "missing"], default="pending")
    p_prepare.add_argument("--batch-size", type=int, default=10)
    p_prepare.add_argument("--offset", type=int, default=None)
    p_prepare.add_argument("--out-dir", default=BATCH_DIR_DEFAULT)
    p_prepare.add_argument("--batch-number", type=int, default=1)
    p_prepare.add_argument("--stdout-prompt", action="store_true")
    p_prepare.add_argument("--no-files", action="store_true")
    p_prepare.add_argument("--quiet", action="store_true")
    p_prepare.set_defaults(func=cmd_prepare_batch)

    p_import = sub.add_parser("import-batch", help="Import local analysis JSON into Redis")
    p_import.add_argument("--file", required=True)
    p_import.add_argument("--dry-run", action="store_true")
    p_import.add_argument("--strict", action="store_true")
    p_import.set_defaults(func=cmd_import_batch)

    p_status = sub.add_parser("batch-status", help="Show pending queue stats")
    p_status.add_argument("--peek", type=int, default=10)
    p_status.set_defaults(func=cmd_batch_status)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
