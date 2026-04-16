# Lyricist

Scheduled worker that syncs a YT Music playlist and generates public-safe lyric notes:

- background analysis (no lyric quoting)
- flashcard-ready vocabulary (no lyric quoting)

Outputs are written to Redis (DragonflyDB) for `apps/api` + `apps/web` to serve.

## Modes

Set `LYRICIST_MODE`:

- `sync`: ingest playlist tracks and enqueue pending analysis
- `analyze`: process pending queue with rate-limited LLM calls
- `all`: run sync, then analyze

## Missing tracks

The sync uses `ytmusicapi` unauthenticated. Tracks that are Premium-only, private, region-restricted, or otherwise unavailable come back from the playlist endpoint as placeholders with no `videoId` and no `title`, so `_extract_track` drops them. The skip is logged as `lyricist.track.skipped_unavailable` with whatever metadata ytmusicapi returned.

Expected side effect: the Redis index can be smaller than the playlist's `trackCount` reported by YouTube Music. This is not a bug; it is the cost of running without auth.

To close the gap, authenticate ytmusicapi (`ytmusicapi oauth` → `oauth.json`, pass path to `YTMusic(...)`). Refresh tokens last until revoked. The cronjob would need the credential file mounted as a secret. Consider using a secondary Google account to limit blast radius rather than your primary account.

## Manual batch workflow

The `lyricist-manual-analysis` CLI exports Redis-backed batches and imports cached JSON analysis:

```bash
uv run --project apps/lyricist lyricist-manual-analysis prepare-batch --source pending --batch-size 10 --batch-number 1
uv run --project apps/lyricist lyricist-manual-analysis import-batch --file tmp/lyricist-batches/batch-001.response.json
uv run --project apps/lyricist lyricist-manual-analysis batch-status --peek 10
```

`prepare-batch` pages by `--batch-number` by default (`offset = (batch-number - 1) * batch-size`).
Pass `--offset` only when you need manual cursor control.

For an interactive clipboard workflow (copy prompt -> paste JSON -> final single import):

```bash
cd apps/lyricist
./scripts/manual-analysis-clipboard.sh --source missing --batch-size 10
```

Python end-to-end automation mode (Gemini same-chat edit flow):

```bash
cd apps/lyricist
uv run --with playwright playwright install chromium
uv run --with playwright python ./scripts/manual-analysis-gemini.py \
  --source missing \
  --batch-size 10 \
  --gemini-url "https://gemini.google.com/app"
```

The script handles prepare-batch, Gemini prompt edit/send/wait/copy, response validation,
and final import in one run. It uses a persistent Chromium profile at
`~/.cache/lyricist-gemini-playwright` by default, creates a new chat when no chat URL
is configured, and stores the selected chat URL in
`~/.cache/lyricist-gemini-playwright/chat_url.txt` for reuse.

The shell workflow (`./scripts/manual-analysis-clipboard.sh`) is still available as fallback.

## LRCLIB Bulk Export

For full offline/manual analysis, download LRCLIB's official DB dump(s):

```bash
cd <repo-root>
./apps/lyricist/scripts/fetch_lrclib_dumps.sh
```

Defaults:

- manifest: `apps/lyricist/scripts/tmp/lrclib/dumps/manifest.json`
- dump files: `apps/lyricist/scripts/tmp/lrclib/dumps/*.sqlite3.gz`

The download script is resumable via HTTP range requests (`curl -C -`).

If you specifically want JSONL pulled record-by-record from `/api/get/{id}`:

```bash
python ./apps/lyricist/scripts/fetch_lrclib_dump.py --resume
```
