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
- Jobs: `job:{id}` and field keys like `job:{id}:title`.
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
- Mandatory labels: `app: portfolio`, `component: [api|web|db|collector|upworker]`.
- Resources: always define requests/limits (start low: 128Mi RAM).
- Probes:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 3000
  initialDelaySeconds: 5
```

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
- Example: `feat(upworker): add upwork graphql ingestion`.

---

## 6.5. Build Check Discipline

- After refactors or UI changes, run the relevant build(s) for the affected app(s).
- Example: `pnpm -C apps/web build`.
- If the build fails, fix issues and re-run until it passes.
- Run lint before finalizing changes and fix violations:
  - `pnpm lint` for monorepo TypeScript/Astro/Python lint checks.
  - If scope is limited, run the minimal relevant lint command(s) and mention what was run.

---

## 7. Worker Apps (Python)

- `apps/upworker`: Upwork ingestion worker (Python + uv).
- `apps/collector`: Personal data collectors (Python + uv).
- Keep these apps small and task-focused; add a new app only when a task has distinct dependencies or runtime needs.
- Prefer K8s CronJobs for scheduled runs; long-lived services should stream updates to Redis and the API can expose them.

---

## 8. Web Dev Performance Notes

- Avoid barrel imports from `@lucide/astro` in dev. Prefer per-icon imports like `@lucide/astro/icons/menu` to prevent large module scans and slow TTFB.

---

## 9. Commit Hygiene

- Do not mix unrelated changes in a single commit. Separate documentation/agent-rule updates from code formatting changes.
