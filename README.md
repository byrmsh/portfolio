# Portfolio

A living portfolio and infrastructure dashboard.

## Local Development

1. Install dependencies:

```bash
pnpm install
```

2. Start services:

```bash
pnpm --filter api dev
pnpm --filter web dev
```

3. Optional: run DragonflyDB locally:

```bash
docker run -p 6379:6379 docker.dragonflydb.io/dragonflydb/dragonfly
```

## Workers (uv)

```bash
cd apps/upworker
uv venv
uv sync
uv run upworker
```

## Docker Compose (Optional)

```bash
docker compose up --build
```

Services:
- `web`: http://localhost:4321
- `api`: http://localhost:3000
- `redis` (DragonflyDB): localhost:6379
- `upworker`: Upwork ingestion worker
