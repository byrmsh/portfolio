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

## Feature Groups & Checklist

Frontend Experience:
- [ ] Initialize Astro project in `apps/web`.
- [ ] Create a Bento Grid layout using CSS Grid + Tailwind.
- [ ] Component: `StatusCard.svelte` (placeholder for live infra stats).
- [ ] Component: `SocialLink.svelte` (GitHub, Email, PGP).
- [ ] Output: a static site running on `localhost:4321`.

API & Data Layer:
- [ ] Initialize Hono app in `apps/api`.
- [ ] Create `deploy/k8s/db.yaml` (DragonflyDB StatefulSet).
- Constraint: use `hostPath` initially (single-node K3s) or `local-path` StorageClass.
- [ ] Implement `GET /health` in API.
- [ ] Containerize API and deploy to K8s.
- [ ] Integration task: update `homelab/infra/tunnel.ts` to point Cloudflare Tunnel to the API service.

Workers & Live Data:
- [ ] Create a scraper cron function in a separate worker app.
- Sources: Upwork RSS / GitHub GraphQL API.
- Sink: DragonflyDB.
- [ ] Update `StatusCard.svelte` to fetch from real API.
- [ ] Add infrastructure visualizer (K8s node status).

Personal Metrics & Content:
- [x] Fetch personal metrics (Anki streak grid, GitHub streak grid).
- [ ] Fetch YT Music saved playlist and generate lyric/lore pages (Genius-like, but personal).
- [ ] Ingest cluster info and surface it on the dashboard.
- [ ] Keep observability data (logs/metrics/traces) separate from personal stats content.

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
