# Upworker

Upworker is a lightweight worker for ingesting Upwork job data into Redis.

## Local Setup (uv)

1. Create a virtual environment and install deps:

```bash
uv venv
uv sync
```

2. Copy env sample:

```bash
cp .env.sample .env
```

3. Run the worker:

```bash
uv run upworker
```

## Redis Stream Notes

Upworker writes full job JSON to `job:{id}` keys and emits a lightweight entry to the Redis
stream defined by `REDIS_STREAM_KEY` (default `jobs`). Each stream entry ID is the Upwork
job ID plus a `-0` suffix to match Redis stream ID format.
