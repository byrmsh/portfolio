# portfolio Helm chart

## Local workflow

```bash
# Build local images + load into minikube + helm upgrade/install + rollout checks
pnpm k8s:local:apply
```

Secrets are intentionally not in chart values/templates. Create/update Kubernetes Secrets separately (see root `README.md`).

## Web SSR Origins (Avoid Hairpin)

Some web widgets fetch JSON endpoints during SSR (for example `/system-status.json`).

- `web.env.webOrigin` feeds `WEB_ORIGIN` for SSR absolute URLs.
  - Recommended in-cluster value is an in-pod origin like `http://127.0.0.1:8080` (chart default) to avoid hairpinning out via ingress/Cloudflare.
- `web.env.apiOrigin` feeds `API_ORIGIN` for server-side calls to the API (default `http://api-service:3000`).

## Upworker / UpworkerBot Secrets

Examples (fill in your own values):

```bash
kubectl create secret generic upworker-secrets \
  --namespace portfolio \
  --from-literal=UPWORK_BEARER_TOKEN='YOUR_UPWORK_TOKEN'
```

```bash
kubectl create secret generic upworker-bot-secrets \
  --namespace portfolio \
  --from-literal=TELEGRAM_BOT_TOKEN='YOUR_TOKEN' \
  --from-literal=TELEGRAM_ALLOWED_CHAT_ID='YOUR_CHAT_ID' \
  --from-literal=UPWORKERBOT_HTTP_TOKEN='OPTIONAL_HTTP_TOKEN' \
  --dry-run=client -o yaml | kubectl apply -f -
```

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
