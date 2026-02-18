# AGENTS.md - Coding Agent Rules

## 1. Purpose

This file defines constraints and operating rules for coding agents. Project architecture and human-facing docs live in `README.md`.

---

## 2. Homelab Contract

- Do not provision infrastructure (servers, SSH keys, Cloudflare Tunnels).
- Do build images, write K8s manifests, and implement application logic.
- Ingress handshake: this repo creates a K8s `Service` (ClusterIP). The user must update `homelab/infra/tunnel.ts` to point the Cloudflare Tunnel at the internal Service IP/Port.

---

## 3. Data & Storage Rules

- Database: DragonflyDB (Redis API). Use `ioredis` client in the API.
- Keyspacing: use colons `entity:id:attribute` (e.g., `job:1024:title`).
- Personal data: `stat:{source}:{id}` (non-observability metrics).
- Observability: do not store logs/metrics/traces in Redis. Use Grafana stack + OpenTelemetry pipeline instead.
- Shared schemas:
  - TypeScript validators/types belong in `packages/schema`.
  - Python validators/types belong in `packages/schema-py`.
  - App-local files should be thin bridges/re-exports, not separate schema sources.

---

## 4. Kubernetes Manifest Rules

- Namespace: `portfolio`.
- Naming: `app-name-resource` (e.g., `api-deployment`, `web-service`).
- Mandatory labels: `app: portfolio`, `component: [api|web|db|collector|lyricist]`.
- Resources: always define requests/limits (start low: 128Mi RAM).
- Probes:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 3000
  initialDelaySeconds: 5
```

### 4.1 Helm-First Deployment

- Deployment source is `deploy/helm/portfolio`.
- When changing workloads, update Helm templates/values and related docs in the same task.

### 4.2 Default Local Dev Workflow

- Default loop: run web on host and connect to minikube API via port-forward.
- Command: `pnpm dev` (root).
- Bootstrap/update local cluster workloads with: `pnpm k8s:local:apply`.

---

## 5. Secret Management

The agent must **NEVER** write secrets to YAML. Instead, output a shell command for the user. Example:

```bash
kubectl create secret generic db-credentials \
  --namespace portfolio \
  --from-literal=password='YOUR_SECURE_PASSWORD'
```

---

## 6. Git & Commit Conventions

- Use Conventional Commits for all changes.
- Format: `type(scope): summary`.
- `scope` should name the most relevant area (app/package/docs folder). It does not have to be a microservice name; omit the scope if unclear.
- Example: `feat(collector): add cluster snapshot collector`.

---

## 6.5. Build Check Discipline

- Do not run `prek run` right before commit by default; `git commit` already runs pre-commit hooks in this repo.
- Run `prek run --all-files` only when you need an explicit manual validation pass without committing (or when requested).
- If `.pre-commit-config.yaml` changes, run `prek validate-config`.
- After refactors or UI changes, run the relevant build(s) for affected app(s).
- Example build check: `pnpm -C apps/web build`.
- If a build fails, fix issues and re-run until it passes.
- Local Python smoke tests should use `uv run --env-file .env ...` (or a temp env file) instead of overwriting repo `.env` files.

---

## 7. Worker Apps (Python)

- `apps/collector`: Personal data collectors (Python + uv).
- Keep these apps small and task-focused; add a new app only when a task has distinct dependencies or runtime needs.
- Prefer K8s CronJobs for scheduled runs; long-lived services should stream updates to Redis and the API can expose them.

---

## 8. Web Dev Performance Notes

- Avoid barrel imports from `@lucide/astro` in dev. Prefer per-icon imports like `@lucide/astro/icons/menu` to prevent large module scans and slow TTFB.

---

## 9. Commit Hygiene

- Do not mix unrelated changes in a single commit. Separate documentation/agent-rule updates from code formatting changes.
- Use multiple commits when changes span distinct concerns (e.g., repo hygiene vs app behavior vs docs).
