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

### Local Minikube (Recommended for this repo)

`deploy/k8s/04-web.yaml` uses `image: portfolio-web:dev`, so your local build must use the same tag unless you change the manifest.

Quick commands:

```bash
# First-time/full local deploy (build all images, load, apply, wait)
pnpm k8s:local:apply

# Fast web-only update loop (build web image, load, restart, wait)
pnpm k8s:local:web
```

1. Build local images:

```bash
docker build -f apps/api/Dockerfile -t portfolio-api:dev .
docker build -f apps/web/Dockerfile -t portfolio-web:dev .
docker build -f apps/collector/Dockerfile -t portfolio-collector:dev .
docker build -f apps/ankiworker/Dockerfile -t portfolio-ankiworker:dev .
docker build -f apps/lyricist/Dockerfile -t portfolio-lyricist:dev .
```

2. Load images into Minikube:

```bash
minikube image load portfolio-api:dev
minikube image load portfolio-web:dev
minikube image load portfolio-collector:dev
minikube image load portfolio-ankiworker:dev
minikube image load portfolio-lyricist:dev
```

3. Create/update secrets from local `.env` files (no values in YAML):

```bash
python3 - <<'PY'
from pathlib import Path

def normalize_env(src: str, dst: str) -> None:
    out = []
    for raw in Path(src).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
            v = v[1:-1]
        out.append(f"{k}={v}")
    Path(dst).write_text("\n".join(out) + ("\n" if out else ""))

normalize_env("apps/collector/.env", "/tmp/collector.k8s.env")
normalize_env("apps/lyricist/.env", "/tmp/lyricist.k8s.env")
PY

kubectl -n portfolio create secret generic collector-secrets \
  --from-env-file=/tmp/collector.k8s.env \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n portfolio create secret generic lyricist-secrets \
  --from-env-file=/tmp/lyricist.k8s.env \
  --dry-run=client -o yaml | kubectl apply -f -
rm -f /tmp/collector.k8s.env /tmp/lyricist.k8s.env
```

4. Apply manifests:

```bash
kubectl apply -f deploy/k8s/
```

5. Check rollout:

```bash
kubectl -n portfolio rollout status deploy/db-deployment
kubectl -n portfolio rollout status deploy/api-deployment
kubectl -n portfolio rollout status deploy/web-deployment
```

6. Trigger CronJobs manually (while `suspend: true`):

```bash
ts=$(date +%s)
for cj in collector-anki-cronjob collector-cluster-cronjob collector-github-cronjob lyricist-cronjob; do
  kubectl -n portfolio create job --from=cronjob/$cj ${cj/-cronjob/}-manual-$ts
done
```

7. Optional local access:

```bash
kubectl -n portfolio port-forward svc/api-service 3000:3000
kubectl -n portfolio port-forward svc/web-service 8080:80
```

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
kubectl -n portfolio rollout restart deployment/api-deployment
kubectl -n portfolio rollout restart deployment/web-deployment
```
