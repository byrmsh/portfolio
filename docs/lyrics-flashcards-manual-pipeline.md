# Lyrics Flashcards + Manual Analysis Pipeline

Status: implemented in repo (pre-prod workflow).

## What changed

1. Flashcards on lyric note pages are now swipe-first in the web UI.
2. Lyricist is split into two phases:

- `sync`: ingest playlist songs and enqueue pending analysis.
- `analyze`: process pending queue with rate-limited LLM calls.

3. Manual batch tooling is available for exporting Redis-backed song batches to prompt files and importing cached analysis JSON.

## Data contract (strict)

Each `analysis.vocabulary[]` item now requires:

```json
{
  "id": "string",
  "term": "string",
  "exampleDe": "string",
  "literalEn": "string",
  "meaningEn": "string",
  "exampleEn": "string",
  "cefr": "string (optional)",
  "memoryHint": "string (optional)",
  "usage": ["string"]
}
```

Shared schemas are updated in:

- `packages/schema/src/dashboard.ts`
- `packages/schema-py/src/portfolio_schema/dashboard.py`

## Redis keys

- Saved note: `stat:ytmusic:{trackId}`
- Analysis: `stat:ytmusic:{trackId}:analysis`
- Saved index: `index:ytmusic:saved`
- Pending analysis queue: `index:ytmusic:analysis:pending`

## Lyricist modes

Configure via `LYRICIST_MODE`:

- `sync`
- `analyze`
- `all`

Rate-limit controls:

- `LYRICIST_ANALYSIS_MAX_PER_RUN`
- `LYRICIST_ANALYSIS_MIN_INTERVAL_SECONDS`
- `LYRICIST_ANALYSIS_BACKOFF_BASE_SECONDS`
- `LYRICIST_ANALYSIS_BACKOFF_MAX_SECONDS`
- `LYRICIST_ANALYSIS_MAX_ATTEMPTS`

## Manual workflow

Use `apps/lyricist/manual_analysis.py`.

### 1) Prepare batch files from Redis

```bash
uv run --project apps/lyricist lyricist-manual-analysis prepare-batch \
  --source pending \
  --batch-size 10 \
  --offset 0 \
  --batch-number 1
```

Outputs:

- `batch-001.input.json`
- `batch-001.prompt.txt`
- `batch-001.response.template.json`

Paste prompt into Gemini/AI Studio/ChatGPT web and save the JSON response locally.

### 2) Import cached analysis JSON into Redis

```bash
uv run --project apps/lyricist lyricist-manual-analysis import-batch \
  --file tmp/lyricist-batches/batch-001.response.json
```

Dry-run mode:

```bash
uv run --project apps/lyricist lyricist-manual-analysis import-batch \
  --file tmp/lyricist-batches/batch-001.response.json \
  --dry-run
```

### 3) Inspect queue

```bash
uv run --project apps/lyricist lyricist-manual-analysis batch-status --peek 10
```

## Helm deployment notes

The chart now defines two lyricist cronjobs:

- `lyricist-sync-cronjob`
- `lyricist-analysis-cronjob`

Both use `lyricist-secrets`; mode is injected by per-job env in values.
