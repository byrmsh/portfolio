# Collector

Python collectors that write personal stats into Redis (DragonflyDB) for the portfolio API/web.

## Entrypoints

Collector commands are defined in `apps/collector/pyproject.toml`:

- `collector-github` (GitHub contributions activity, 16x7 daily grid)
- `collector-ytmusic` (placeholder; writes a stub record)
- `collector-cluster` (placeholder; writes a stub record)

## Local Development (uv)

```bash
uv venv
uv sync
cp .env.sample .env
uv run --env-file .env collector-github
```

All required environment variables live in `.env.sample` (treat it as the source of truth).

## Schemas

The collectors write JSON payloads that the API/web can validate.

- Source of truth: `packages/schema-py` (installed here as the `portfolio-schema` dependency; see `apps/collector/pyproject.toml`).
- Import path used by collectors: `apps/collector/schema.py` (thin re-export of the shared schemas).
- The activity collectors write an `ActivitySeries` record (cells + optional streak + timestamps).

## Redis Writes (Current)

- Activity series live under `stat:{source}:default` (ex: `stat:github:default`, `stat:anki:default`).
- Collectors emit a lightweight notification event to a Redis Stream (`REDIS_EVENTS_STREAM`, default `events`) with:
  - `type`: e.g. `github_activity_updated`
  - `payload`: JSON like `{ "key": "stat:github:default" }`

Per collector:
- `collector-github` (`github_activity.py`): GitHub GraphQL contributions calendar -> `stat:github:default` and `github_activity_updated`.
- `collector-ytmusic` (`ytmusic.py`): placeholder -> `metric:ytmusic:playlist` and `ytmusic_playlist_updated`.
- `collector-cluster` (`cluster.py`): placeholder -> `metric:cluster:status` and `cluster_status_updated`.

Anki review activity was split into `apps/ankiworker` (separate dependencies and image).
