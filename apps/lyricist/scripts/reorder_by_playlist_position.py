"""One-shot: reconcile lyric-note Redis state with the current YT Music playlist.

Three passes:

  1. Prune stale Redis entries whose track id is not in the current playlist
     (handles YT Music swapping a song's videoId after a region change).

  2. Stamp playlist tracks that are missing from Redis using
     ``_compute_position_scores`` so they slot in between their position
     neighbors instead of getting "now".

  3. Walk the playlist bottom-up and clamp any existing track whose score
     violates the monotonic order. Idempotent. Tracks already in correct
     order are left alone.

Convention for this playlist: lower playlist position = older add, higher
position = newer add. Score increases with position; the bottom track wins
zrevrange.

Usage:
    REDIS_URL=redis://localhost:6379/0 \\
    YTMUSIC_PLAYLIST_ID=... \\
    uv run python scripts/reorder_by_playlist_position.py [--apply]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from portfolio_common import emit_event, redis_client
from portfolio_schema import RedisKeys
from ytmusicapi import YTMusic

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lyricist import (  # noqa: E402
    _compute_position_scores,
    _extract_track,
    _migrate_alias_ids,
    _prune_removed_tracks,
    _upsert_saved_note_and_index,
)


def _ts_to_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _preview_migrate_alias_ids(r, tracks) -> int:
    from lyricist import _fingerprint  # noqa: PLC0415

    fp_to_track = {}
    for t in tracks:
        fp_to_track.setdefault(_fingerprint(t.title, t.artist), t)
    playlist_ids = {t.id for t in tracks}
    count = 0
    for rid in r.zrange(RedisKeys.INDEX_LYRICS_RECENT, 0, -1):
        old_id = rid.decode() if isinstance(rid, (bytes, bytearray)) else str(rid)
        if not old_id or old_id in playlist_ids:
            continue
        raw = r.get(RedisKeys.stat("ytmusic", old_id))
        if not raw:
            continue
        try:
            data = json.loads(raw.decode() if isinstance(raw, (bytes, bytearray)) else raw)
        except Exception:
            continue
        target = fp_to_track.get(_fingerprint(data.get("title", ""), data.get("artist", "")))
        if not target or target.id == old_id:
            continue
        if r.exists(RedisKeys.stat("ytmusic", target.id)):
            continue
        score = r.zscore(RedisKeys.INDEX_LYRICS_RECENT, old_id)
        print(
            f"  ~ {data.get('title')!r} - {data.get('artist')!r}: {old_id} -> {target.id}  "
            f"score={int(score) if score else 'n/a'}"
        )
        count += 1
    return count


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Write changes. Without this, dry-run.")
    args = ap.parse_args()

    playlist_id = os.environ.get("YTMUSIC_PLAYLIST_ID", "")
    if not playlist_id:
        print("YTMUSIC_PLAYLIST_ID not set", file=sys.stderr)
        return 2

    pl = YTMusic().get_playlist(playlist_id, limit=200)
    tracks_raw = pl.get("tracks") or []
    tracks = [_extract_track(t) for t in tracks_raw if isinstance(t, dict)]
    tracks = [t for t in tracks if t]
    if not tracks:
        print("playlist is empty", file=sys.stderr)
        return 1

    r = redis_client()
    playlist_ids = {t.id for t in tracks}

    # --- 0. Migrate aliases: if an existing Redis entry has the same title+artist
    # as a playlist track with a different videoId, rename it under the new id and
    # preserve its score. Required because YT Music swaps videoIds for the same song.
    if args.apply:
        migrated = _migrate_alias_ids(r, tracks)
    else:
        migrated = _preview_migrate_alias_ids(r, tracks)

    # --- 1. Prune
    stale = []
    for rid in r.zrange(RedisKeys.INDEX_LYRICS_RECENT, 0, -1):
        tid = rid.decode() if isinstance(rid, (bytes, bytearray)) else str(rid)
        if tid and tid not in playlist_ids:
            stale.append(tid)

    # --- 2. New tracks (in playlist, not in Redis)
    new_tracks = [t for t in tracks if not r.exists(RedisKeys.stat("ytmusic", t.id))]
    new_scores = _compute_position_scores(r, tracks, new_tracks) if new_tracks else {}

    # --- 3. Monotonic clamp on existing tracks (after hypothetical insert of new ones)
    # Build a unified score map: existing scores from Redis, planned scores for new tracks.
    score_by_id: dict[str, int] = {}
    for t in tracks:
        if t.id in new_scores:
            score_by_id[t.id] = new_scores[t.id]
            continue
        s = r.zscore(RedisKeys.INDEX_LYRICS_RECENT, t.id)
        if s is not None:
            score_by_id[t.id] = int(s)

    prev_score: int | None = None
    clamps: list[tuple[int, str, str, int, int]] = []
    for i in range(len(tracks) - 1, -1, -1):
        t = tracks[i]
        if t.id not in score_by_id:
            continue
        existing = score_by_id[t.id]
        new_score = existing if prev_score is None else min(existing, prev_score - 1)
        if new_score != existing and t.id not in new_scores:
            clamps.append((i, t.id, f"{t.title} - {t.artist}", existing, new_score))
        score_by_id[t.id] = new_score
        prev_score = new_score
    clamps.sort(key=lambda c: c[0])

    print(f"playlist tracks: {len(tracks)}")
    print(f"alias migrations: {migrated}")
    # In dry-run, the previewed migrations have not actually been applied, so
    # the entries below still appear under their old ids until --apply runs.
    print(f"prune (stale ids in redis, not in playlist): {len(stale)}")
    for tid in stale:
        raw = r.get(RedisKeys.stat("ytmusic", tid))
        label = ""
        if raw is not None:
            data = raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
            try:
                n = json.loads(data)
                label = f"  ({n.get('title')!r} - {n.get('artist')!r})"
            except Exception:
                pass
        print(f"  - {tid}{label}")

    print(f"\nnew tracks (in playlist, not yet in redis): {len(new_tracks)}")
    for t in new_tracks:
        s = new_scores[t.id]
        pos = next(i for i, x in enumerate(tracks) if x.id == t.id)
        print(f"  + pos={pos:>3}  {t.title} - {t.artist}  id={t.id}  score={s} ({_ts_to_iso(s)})")

    print(f"\nmonotonic clamps on existing entries: {len(clamps)}")
    for pos, tid, label, old, new in clamps:
        print(f"  pos={pos:>3}  {label}")
        print(f"    {old} ({_ts_to_iso(old)}) -> {new} ({_ts_to_iso(new)})")

    if not (stale or new_tracks or clamps):
        print("\nnothing to do")
        return 0
    if not args.apply:
        print("\n(dry-run, pass --apply to write)")
        return 0

    # Apply prune
    _prune_removed_tracks(r, playlist_ids)

    # Apply new-track inserts
    for t in new_tracks:
        _upsert_saved_note_and_index(r, t, score=new_scores[t.id])

    # Apply monotonic clamps (re-fetch since the new inserts may have shifted things,
    # but we already accounted for them in score_by_id above).
    for _pos, tid, _label, _old, new in clamps:
        stat_key = RedisKeys.stat("ytmusic", tid)
        raw = r.get(stat_key)
        if raw is None:
            continue
        note = json.loads(raw.decode() if isinstance(raw, (bytes, bytearray)) else raw)
        note["savedAt"] = _ts_to_iso(new)
        r.set(stat_key, json.dumps(note))
        r.zadd(RedisKeys.INDEX_LYRICS_RECENT, {tid: new})
        emit_event(r, "ytmusic_saved_updated", {"trackId": tid, "key": stat_key})

    print(f"\napplied: pruned={len(stale)} inserted={len(new_tracks)} clamped={len(clamps)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
