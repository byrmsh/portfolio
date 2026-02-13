# Frontend Data Model and Redis Structures

This document maps the current static frontend cards to concrete Redis structures and
runtime contracts.

## 1) Current Frontend Mock Audit

`apps/web/src/pages/index.astro` renders these cards:

1. `ActivityMonitor`:

- GitHub contribution heatmap cells (`level` buckets)
- Anki heatmap cells + streak count

2. `SavedLyricsCard`:

- latest saved track title
- artist
- lyric-note link
- (implicit) saved timestamp

3. `WritingCard`:

- post title
- one-line description
- post URL

4. `KnowledgeGraphCard`:

- node count
- summary text

5. `JobScoutCard`:

- source (Upwork)
- capture age
- job title
- tags

6. `SystemHealthCard`:

- namespace label
- uptime ratio/value
- service list with status/pulse

## 2) Redis Keyspace Decision

These keys follow the repository rules from `AGENTS.md`.

### Jobs

- Primary record: `job:{id}`
- Field keys:
  - `job:{id}:title`
  - `job:{id}:summary`
  - `job:{id}:description`
  - `job:{id}:tags`
  - `job:{id}:publishedAt`
  - `job:{id}:capturedAt`
- Optional index keys:
  - `index:job:recent` (sorted set, score = captured timestamp)

### Personal Stats / Content

- GitHub streak heatmap:
  - `stat:github:{username}`
  - field keys like `stat:github:{username}:cells`

- Anki streak heatmap:
  - `stat:anki:{profileId}` (use `default` if single profile)

- Saved lyrics:
  - `stat:ytmusic:{trackId}`
  - optional index: `index:ytmusic:saved`

- Writing posts:
  - `stat:writing:{slug}`
  - optional index: `index:writing:recent`

- Knowledge graph summary:
  - `stat:obsidian:graph`

- System health summary for UI (not raw telemetry):
  - `stat:cluster:portfolio`

## 3) Contract Files

- TypeScript contracts + validators:
  - canonical: `packages/schema/src/dashboard.ts` and `packages/schema/src/upwork.ts` (Zod + inferred types)
  - app bridges: `apps/api/src/schema/index.ts` and `apps/web/src/schema/index.ts`
- Python contracts + validators:
  - canonical: `packages/schema-py/src/portfolio_schema/dashboard.py` and `packages/schema-py/src/portfolio_schema/upwork.py`
  - app bridges: `apps/collector/schema.py`, `apps/upworker/schema.py`

Both files define:

- card-level UI payloads (`DashboardSnapshot`)
- Redis-oriented records (`JobRedisRecord`, stat records)
- key helper builders (`job`, `job_field`, `stat`, `stat_field`)

## 4) API Shape Recommendation

Serve the frontend from one aggregate endpoint:

- `GET /api/dashboard`
- response: `{ data: DashboardSnapshot, meta: { ts, source } }`

Keep `/api/jobs` and `/api/status` for focused polling paths where needed.

## 5) Observability Boundary

Do not push logs/metrics/traces into Redis. Store only curated, user-facing status
summaries used by the portfolio UI.
