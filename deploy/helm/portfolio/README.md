# portfolio Helm chart

## Local workflow

```bash
# Build local images + load into minikube + helm upgrade/install + rollout checks
pnpm k8s:local:apply
```

Secrets are intentionally not in chart values/templates. Create/update Kubernetes Secrets separately (see root `README.md`).

## Lyricist CronJobs

The chart runs lyricist in two jobs:

- `lyricist-sync-cronjob`: playlist ingest + queueing
- `lyricist-analysis-cronjob`: pending analysis processing

Both jobs read shared secrets from `lyricist-secrets`; mode is set per job in values via env.
Default cadence in this repo is every 4 hours:

- sync at minute `0`
- analyze at minute `10`

## Web SSR Origins (Avoid Hairpin)

Some web widgets fetch JSON endpoints during SSR (for example `/system-status.json`).

- `web.env.webOrigin` feeds `WEB_ORIGIN` for SSR absolute URLs.
  - Recommended in-cluster value is an in-pod origin like `http://127.0.0.1:8080` (chart default) to avoid hairpinning out via ingress/Cloudflare.
- `web.env.apiOrigin` feeds `API_ORIGIN` for server-side calls to the API (default `http://api-service:3000`).
- `web.env.argocdHealthUrl` feeds `ARGOCD_HEALTH_URL` for the Argo CD probe used by `/system-status.json`.
  - Recommended in-cluster value is `http://argocd-server-metrics.argocd.svc.cluster.local:8083/metrics` to avoid TLS trust issues on Argo CD server redirects.

## Install / Upgrade

```bash
helm upgrade --install portfolio ./deploy/helm/portfolio \
  --namespace portfolio \
  --create-namespace
```

## Production values

Production overrides live in the `homelab` repo (GitOps source of truth).

## Validate

```bash
helm lint ./deploy/helm/portfolio
helm template portfolio ./deploy/helm/portfolio --namespace portfolio >/tmp/portfolio-rendered.yaml
```
