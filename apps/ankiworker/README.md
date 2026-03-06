# Ankiworker

Anki-specific collectors that write personal stats into Redis (DragonflyDB) for the portfolio API/web.

## Entrypoints

Commands are defined in `apps/ankiworker/pyproject.toml`:

- `ankiworker-activity` (Anki review activity, last 7 days grid + full-history streak)

## Local Development (uv)

```bash
uv venv
uv sync
cp .env.sample .env
uv run --env-file .env ankiworker-activity
```

All required environment variables live in `.env.sample` (treat it as the source of truth).
