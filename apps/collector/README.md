# Collector

Personal data collectors for the portfolio.

## Scripts

- `collector-anki` (Anki internal API client)
- `collector-github` (GitHub streak grid)
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
