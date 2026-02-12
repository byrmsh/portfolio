# portfolio Helm chart

## Local workflow

```bash
# Build local images + load into minikube + helm upgrade/install + rollout checks
pnpm k8s:local:apply
```

Secrets are intentionally not in chart values/templates. Create/update Kubernetes Secrets separately (see root `README.md`).

## Upworker / UpworkerBot Secrets

Examples (fill in your own values):

```bash
kubectl create secret generic upworker-secrets \
  --namespace portfolio \
  --from-literal=TELEGRAM_BOT_TOKEN='YOUR_TOKEN' \
  --from-literal=TELEGRAM_CHAT_ID='YOUR_CHAT_ID'
```

```bash
kubectl create secret generic upworker-bot-secrets \
  --namespace portfolio \
  --from-literal=TELEGRAM_BOT_TOKEN='YOUR_TOKEN' \
  --from-literal=TELEGRAM_ALLOWED_CHAT_ID='YOUR_CHAT_ID'
```

## Install / Upgrade

```bash
helm upgrade --install portfolio ./deploy/helm/portfolio \
  --namespace portfolio \
  --create-namespace
```

## Production values

```bash
helm upgrade --install portfolio ./deploy/helm/portfolio \
  --namespace portfolio \
  --create-namespace \
  -f deploy/helm/portfolio/values-prod.yaml
```

## Validate

```bash
helm lint ./deploy/helm/portfolio
helm template portfolio ./deploy/helm/portfolio --namespace portfolio >/tmp/portfolio-rendered.yaml
```
