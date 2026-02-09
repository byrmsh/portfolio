# Collector

Personal data collectors for the portfolio.

## Scripts

- `collector-anki` (Anki internal API client)
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
