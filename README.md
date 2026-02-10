# Portfolio

A living portfolio and infrastructure dashboard.

## Mission & Identity

- Goal: build a “living” portfolio that demonstrates Full-Stack & DevOps mastery.
- Philosophy: “Functional Engineering.” The site is not just a brochure; it is a dashboard monitoring the infrastructure it runs on.
- Aesthetic: high-density information, clean typography, monochromatic with a single accent (Vercel/Linear/Cloudflare vibe).

## Architecture

This is a polyglot monorepo containing application code and deployment manifests (not infrastructure provisioning).

### Repo Structure

```text
/
├── apps/
│   ├── web/                # Frontend (Astro 5 + Svelte 5)
│   ├── api/                # Backend (Hono)
│   ├── collector/          # Personal data collectors (Python)
│   └── upworker/           # Upwork ingestion worker (Python)
├── deploy/
│   └── k8s/                # Kubernetes Manifests (GitOps state)
│       ├── 01-namespace.yaml
│       ├── 02-db.yaml
│       ├── 03-api.yaml
│       ├── 04-web.yaml
│       └── 05-collector-cronjobs.yaml
├── packages/               # Reserved for shared UI/Types
└── AGENTS.md               # Coding agent rules
```

### Tech Standards

Frontend (`apps/web`):
- Astro 5
- Svelte 5 (Runes mode preferred)
- Islands architecture; default static HTML, use `client:visible` only for live widgets
- TailwindCSS utility-first (avoid `@apply`, keep class sorting)

Backend (`apps/api`):
- Hono
- Node.js 22 LTS or Bun
- REST JSON endpoints: `/api/status` and `/api/jobs`
- Response format: `{ data: T, meta: { ... } }` or standard HTTP errors

Containerization:
- Base images: `node:22-alpine` or `gcr.io/distroless/nodejs`
- Multi-stage builds required
- Run as non-root (`USER node`)
- Web container port `8080` (service maps `80 -> 8080`)

## TODO / Roadmap

- [ ] Harden local-dev + preview: one command to boot web/api/db/workers and a single env var source-of-truth for origins.
- [ ] Formalize Redis schemas + migrations for “content” records (jobs, writing, lyric notes) so changes are forwards-compatible.
- [ ] Add a minimal admin workflow for content curation (approve/hide/pin items; fix metadata) without hand-editing Redis keys.
- [ ] Improve the lyric note page content process: tighten the workflow + system prompt so notes are consistently useful (better background sections, better vocabulary “usage” guidance, fewer generic filler entries).
- [ ] Lyric notes: add quality gates (track dedupe, language detection, CEFR sanity checks) and a “regenerate for this track” endpoint.
- [ ] Extend collectors: cluster inventory snapshot, service uptime/SLO rollups, and surface it on the dashboard.
- [ ] Observability: keep logs/metrics/traces out of Redis; wire OpenTelemetry -> Grafana stack and link to it from the dashboard.
- [ ] Deployment hygiene: CI build + lint, image tags by git SHA, and K8s manifests updated automatically (or documented manual flow).

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

```bash
cd apps/collector
uv venv
uv sync
uv run collector-github
```

### Activity Monitor Data Flow

The homepage **Activity Monitor** is **rendered at build time** in `apps/web` by fetching the API and embedding the last 7 days into static HTML.

- Collectors (Python, `apps/collector`) write activity series to Redis:
  - `stat:github:default`
  - `stat:anki:default` (via `apps/ankiworker`)
- API (`apps/api`) serves:
  - `GET /api/activity-monitor` -> `{ github, anki }`
- Web (`apps/web`) fetches the API **during build**:
  - Set `API_ORIGIN` (preferred) or `PUBLIC_API_ORIGIN`
  - Local default is `http://localhost:3000`

Collector env vars are listed in `apps/collector/.env.sample` (source of truth).
Ankiworker env vars are listed in `apps/ankiworker/.env.sample` (source of truth).

## Docker Compose (Optional)

```bash
docker compose up --build
```

Services:
- `web`: http://localhost:4321
- `api`: http://localhost:3000
- `redis` (DragonflyDB): localhost:6379
- `upworker`: Upwork ingestion worker
- `collector`: personal data collectors

## Deployment Workflow (Manual GitOps)

1. Build images:

```bash
docker build -f apps/api/Dockerfile -t ghcr.io/byrmsh/portfolio-api:latest .
docker build -f apps/web/Dockerfile -t ghcr.io/byrmsh/portfolio-web:latest .
docker build -f apps/collector/Dockerfile -t ghcr.io/byrmsh/portfolio-collector:latest .
docker build -f apps/ankiworker/Dockerfile -t ghcr.io/byrmsh/portfolio-ankiworker:latest .
docker build -f apps/upworker/Dockerfile -t ghcr.io/byrmsh/portfolio-upworker:latest .
```

2. Push images:

```bash
docker push ghcr.io/byrmsh/portfolio-api:latest
docker push ghcr.io/byrmsh/portfolio-web:latest
docker push ghcr.io/byrmsh/portfolio-collector:latest
docker push ghcr.io/byrmsh/portfolio-ankiworker:latest
docker push ghcr.io/byrmsh/portfolio-upworker:latest
```

3. Apply manifests:

```bash
kubectl apply -f deploy/k8s/
```

4. Restart (if needed):

```bash
kubectl rollout restart deployment/portfolio-api -n portfolio
```
