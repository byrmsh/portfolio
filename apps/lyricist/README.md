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

## Manual batch workflow

The `lyricist-manual-analysis` CLI exports Redis-backed batches and imports cached JSON analysis:

```bash
uv run --project apps/lyricist lyricist-manual-analysis prepare-batch --source pending --batch-size 10 --batch-number 1
uv run --project apps/lyricist lyricist-manual-analysis import-batch --file tmp/lyricist-batches/batch-001.response.json
uv run --project apps/lyricist lyricist-manual-analysis batch-status --peek 10
```

For an interactive clipboard workflow (copy prompt -> paste JSON -> final single import):

```bash
cd apps/lyricist
./scripts/manual-analysis-clipboard.sh --source missing --batch-size 10
```
