# portfolio Helm chart

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
