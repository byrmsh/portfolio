# Portfolio

This repository contains the code for my personal portfolio and its supporting services.

It includes:

- a web app (`apps/web`)
- an API (`apps/api`)
- Python workers that collect and process personal activity data (`apps/collector`, `apps/ankiworker`, `apps/lyricist`)
- Helm manifests for Kubernetes deployment (`deploy/helm/portfolio`)

The infrastructure itself (cluster bootstrap, tunnels, GitOps controllers) lives in a separate homelab repository.

## How the repo is organized

```text
apps/
  web/         Astro + Svelte frontend
  api/         Hono API (Redis/Dragonfly-backed)
  collector/   GitHub + cluster collectors (Python)
  ankiworker/  Anki activity collector (Python)
  lyricist/    YT Music lyric-note worker (Python)
packages/
  schema/      Shared TypeScript schemas
  schema-py/   Shared Python schemas
  common-py/   Shared Python utilities
deploy/
  helm/
    portfolio/ Helm chart used for deployments
scripts/
  local dev + k8s helper scripts
```

## Stack

- Frontend: Astro 5, Svelte 5, Tailwind CSS
- API: Hono + ioredis
- Data store: DragonflyDB (Redis API)
- Workers: Python 3.12 + uv
- Deployment: Kubernetes + Helm
- Image publishing: GitHub Actions to GHCR

## Local development

### Prerequisites

- Node.js 22+
- pnpm
- Python 3.12
- uv
- kubectl
- minikube (default local cluster target)

### Install dependencies

```bash
pnpm install
```

### Apply/refresh local cluster workloads

```bash
pnpm k8s:local:apply
```

### Run the default dev loop

```bash
pnpm dev
```

This starts web on host and connects it to API running in your local cluster through port-forwarding.

If you use a non-default kube context:

```bash
K8S_CONTEXT=your-context pnpm dev
```

### Optional: run Dragonfly locally

```bash
docker run -p 6379:6379 docker.dragonflydb.io/dragonflydb/dragonfly
```

## Workers

Each worker has its own `.env.sample` and README:

- `apps/collector/.env.sample`
- `apps/ankiworker/.env.sample`
- `apps/lyricist/.env.sample`

Example run:

```bash
uv run --project apps/collector collector-github
```

## Build checks

```bash
pnpm -C apps/api build
pnpm -C apps/web build
```

## Deployment notes

This repo is Helm-first for workloads:

- chart path: `deploy/helm/portfolio`
- local apply shortcut: `pnpm k8s:local:apply`

Production GitOps ownership is split:

- this repo defines application workloads
- homelab repo owns Argo CD app definitions, production values, and ingress/tunnel wiring

For Cloudflare Tunnel integration, this repo provides a ClusterIP service and the tunnel target is configured in the homelab repo.

## Secrets

Secrets are not stored in YAML. Create Kubernetes secrets with commands such as:

```bash
kubectl create secret generic collector-secrets \
  --namespace portfolio \
  --from-env-file=apps/collector/.env
```

## TODO

- Switch the Live Infrastructure widget to use Grafana as its source of truth (instead of app-side probing).
