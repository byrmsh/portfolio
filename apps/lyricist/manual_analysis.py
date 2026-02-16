from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from environs import env
from pydantic import ValidationError

# Load .env before importing shared modules that read env vars at import time.
env.read_env(recurse=False)

from portfolio_common import redis_client
from portfolio_schema import RedisKeys, YtMusicAnalysis, YtMusicVocabularyItem


BATCH_DIR_DEFAULT = "tmp/lyricist-batches"
PENDING_ZSET_KEY = getattr(RedisKeys, "INDEX_LYRICS_ANALYSIS_PENDING", "index:ytmusic:analysis:pending")
_MD_LINK_RE = re.compile(r"^\[([^\]]+)\]\(([^)]+)\)$")

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
    if label.startswith("http://") or label.startswith("https://"):
        parsed = urlparse(href)
        if parsed.netloc.endswith("google.com") and parsed.path == "/search":
            q = parse_qs(parsed.query).get("q", [])
            if q and q[0].strip() == label:
                return label
    return href


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


def _build_prompt(tracks: list[TrackSeed]) -> str:
    tracks_json = json.dumps([asdict(t) for t in tracks], ensure_ascii=False, indent=2)
    return (
        "You are generating strict JSON for flashcard-ready German vocabulary analysis.\n"
        "Use web/search tools to find lyrics for each exact track before choosing terms.\n"
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
    ids = _collect_batch_ids(r, args.source, args.batch_size, args.offset)
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
    p_prepare.add_argument("--offset", type=int, default=0)
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
