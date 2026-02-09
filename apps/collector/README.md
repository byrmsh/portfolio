# Collector

Personal data collectors for the portfolio.

## Scripts

- `collector-anki` (Anki activity from local `collection.anki2` or AnkiWeb sync)
- `collector-github` (GitHub contributions activity, 16x7 grid)
- `collector-ytmusic` (YT Music playlist ingestion)
- `collector-cluster` (cluster health + nodes)

## Local Setup (uv)

```bash
uv venv
uv sync
cp .env.sample .env
```

Run a collector:

```bash
uv run collector-github
```

GitHub requires a token:

```bash
export GITHUB_USERNAME="your-login"
export GITHUB_TOKEN="ghp_..."
```

Anki activity requires a path to your local `collection.anki2`:

```bash
export ANKI_COLLECTION_PATH="$HOME/.local/share/Anki2/User 1/collection.anki2"
# Optional: affects which calendar day a review lands on.
export ANKI_TIMEZONE="America/Los_Angeles"
```

If `ANKI_COLLECTION_PATH` is not set, the collector will attempt to sync a disposable
collection from AnkiWeb using:

```bash
export ANKIWEB_EMAIL="you@example.com"
export ANKIWEB_PASSWORD="..."
# Optional: where the synced collection lives (persist this in K8s/GHA if you want incremental sync).
export ANKI_SYNC_DIR="/tmp/anki-sync"
# Optional: override sync endpoint (default is AnkiWeb).
export ANKI_SYNC_ENDPOINT=""
```
