# AGENTS.md - Digital Garden Engineering Guidelines

## 1. Project Mission & Identity

> **Goal:** Build a "living" portfolio that demonstrates Full-Stack & DevOps mastery.
> **Philosophy:** "Functional Engineering." The site is not just a brochure; it is a dashboard monitoring the very infrastructure it runs on.
> **Aesthetic:** High-density information, clean typography, monochromatic with single accent (think Vercel/Linear/Cloudflare). No "hacker" gimmicks.

---

## 2. Architecture & The "Homelab" Contract

This repository is a **Polylithic Monorepo**. It contains the Application Code and Deployment Manifests, but **not** the Infrastructure provisioning.

### 2.1 The "Interface" with `homelab` Repo

We rely on the `homelab` repository for the physical reality of the cluster.

- **We Do Not:** Create servers, configure SSH keys, or manage Cloudflare Tunnels directly.
- **We Do:** Build container images, write K8s manifests, and define Application Logic.
- **Ingress Handshake:**
  - This repo creates a K8s **Service** (ClusterIP).
  - _Action Required:_ We must instruct the user to update `homelab/infra/tunnel.ts` to point the Cloudflare Tunnel to this internal Service IP/Port.
- **Secrets:**
  - We assume secrets (DB passwords, API keys) exist in the cluster as K8s Secrets.
  - We reference them via `envFrom` or `secretKeyRef`.

---

## 3. Repository Structure (pnpm Workspaces)

```text
/
├── apps/
│   ├── web/                # Frontend (Astro 5 + Svelte 5)
│   │   ├── src/
│   │   │   ├── components/ # Astro & Svelte components
│   │   │   ├── layouts/    # Page layouts
│   │   │   └── pages/      # File-based routing
│   │   └── Dockerfile      # Multistage build (Node -> Nginx/Node)
│   └── api/                # Backend (Hono)
│       ├── src/
│       │   ├── routes/     # Route definitions
│       │   └── db/         # DragonflyDB/Redis connection
│       └── Dockerfile      # Bun or Node Distroless build
├── deploy/
│   └── k8s/                # Kubernetes Manifests (The "GitOps" State)
│       ├── 01-namespace.yaml
│       ├── 02-db.yaml      # DragonflyDB StatefulSet + PVC
│       ├── 03-api.yaml     # Deployment + Service
│       └── 04-web.yaml     # Deployment + Service
├── packages/               # (Reserved for shared UI/Types)
└── AGENTS.md               # This file

```

---

## 4. Technology Standards

### 4.1 Frontend (`apps/web`)

- **Core:** Astro 5.
- **Interactivity:** Svelte 5 (Runes mode preferred).
- **Hydration:** Use "Islands Architecture" strictly.
- Default: Static HTML (Zero JS).
- Interactive: `<Component client:visible />` (only for things like live status dots or charts).

- **Styling:** TailwindCSS.
- Use `class` sorting (Prettier plugin).
- Avoid `@apply` in CSS files; keep styles utility-first in markup.

- **Data Fetching:**
- **Build Time:** `await fetch()` inside Astro frontmatter (SSG/ISR).
- **Client Time:** Fetch from `/api/...` inside Svelte components for live telemetry.

### 4.2 Backend (`apps/api`)

- **Framework:** Hono (Lightweight, standards-compliant).
- **Runtime:** Node.js 22 (LTS) or Bun (if performance demands it).
- **API Design:** REST (JSON).
- Endpoints: `/api/status` (Infra health), `/api/jobs` (Scraped data).
- Response Format: `{ data: T, meta: { ... } }` or standard HTTP errors.

- **Database:** DragonflyDB (Redis API).
- Use `ioredis` client.
- Keyspacing: Use colons `entity:id:attribute` (e.g., `job:1024:title`).

### 4.3 Containerization

- **Base Images:** `node:22-alpine` or `gcr.io/distroless/nodejs`.
- **Optimization:** Multi-stage builds are mandatory to keep images small.
- **Security:** run as non-root user (`USER node`).
- **Web Runtime:** Use an unprivileged web server image; default container port is `8080` (service maps `80 -> 8080`).

---

## 5. Development Workflow

### 5.1 Local Development

1. **Install:** `pnpm install`
2. **Database:** `docker run -p 6379:6379 docker.dragonflydb.io/dragonflydb/dragonfly`
3. **Run:**

- `pnpm --filter api dev` (Port 3000)
- `pnpm --filter web dev` (Port 4321)

### 5.2 Deployment Lifecycle (Manual GitOps)

Until CI/CD is configured, the Agent follows this "Push" workflow:

1. **Build Images:**

```bash
docker build -f apps/api/Dockerfile -t ghcr.io/byrmsh/portfolio-api:latest .
docker build -f apps/web/Dockerfile -t ghcr.io/byrmsh/portfolio-web:latest .
```

2. **Push:** `docker push ...`
3. **Update K8s:**

- Ensure `deploy/k8s/*.yaml` references the new image tag (or `latest` + `imagePullPolicy: Always`).
- `kubectl apply -f deploy/k8s/`

4. **Restart (if needed):**
   `kubectl rollout restart deployment/portfolio-api -n portfolio`

---

## 6. Implementation Roadmap & Checklist

### Phase 1: The "Coming Soon" Page (Frontend Only)

- [ ] Initialize Astro project in `apps/web`.
- [ ] Create a "Bento Grid" layout using CSS Grid + Tailwind.
- [ ] Component: `StatusCard.svelte` (Placeholder for live infra stats).
- [ ] Component: `SocialLink.svelte` (GitHub, Email, PGP).
- [ ] Output: A static site running on `localhost:4321`.

### Phase 2: The Data Layer (Backend + DB)

- [ ] Initialize Hono app in `apps/api`.
- [ ] Create `deploy/k8s/db.yaml` (DragonflyDB StatefulSet).
- **Constraint:** Use `hostPath` for storage initially (simplest for single-node K3s) or `local-path` StorageClass.

- [ ] Implement `GET /health` in API.
- [ ] Containerize API and deploy to K8s.
- [ ] **Integration Task:** Instruct user to map tunnel ingress to this API service.

### Phase 3: The "Live" Connection

- [ ] Create a "Scraper" cron function in the API (or separate worker).
- Source: Upwork RSS / GitHub GraphQL API.
- Sink: DragonflyDB.

- [ ] Update Frontend `StatusCard.svelte` to fetch from real API.
- [ ] Add "Infrastructure" visualizer (Ping K8s API for node status).

---

## 7. Kubernetes Manifest Guidelines

**Naming Convention:**

- Namespace: `portfolio`
- Resources: `app-name-resource` (e.g., `api-deployment`, `web-service`).

**Mandatory Fields:**

1. **Labels:** `app: portfolio`, `component: [api|web|db]`.
2. **Resources:** Always define requests/limits (Start low: 128Mi RAM).
3. **Probes:**

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 3000
  initialDelaySeconds: 5
```

**Secret Management:**
The Agent must **NEVER** write secrets to YAML.
Instead, output a shell command for the user:

```bash
# Agent Output Example:
"Please run this command to configure the database secret:"
kubectl create secret generic db-credentials \
  --namespace portfolio \
  --from-literal=password='YOUR_SECURE_PASSWORD'
```
