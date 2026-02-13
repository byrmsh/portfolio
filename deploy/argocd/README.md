# Argo CD (Helm) Deploys

This repo already has the deployable Helm chart at `deploy/helm/portfolio`.

This folder adds Argo CD `Application` manifests that tell Argo CD to deploy that
Helm chart (instead of running `helm upgrade --install ...` by hand).

## Local (Minikube)

Prereqs:

- `minikube` running
- `kubectl`

Install Argo CD into your current cluster and create the local `Application`:

```bash
pnpm k8s:local:argocd:bootstrap
```

Then:

```bash
kubectl -n argocd get pods
kubectl -n argocd port-forward svc/argocd-server 8088:443
```

Initial admin password:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d; echo
```

Open https://localhost:8088 and log in as `admin`.

Notes:

- `deploy/argocd/applications/portfolio-local.yaml` uses `repoURL:
  https://github.com/byrmsh/portfolio.git`.
  - If the repo is private, Argo CD will need repo credentials (SSH deploy key
    or a GitHub token) before it can sync.
- For a GitHub token (recommended for local), you can create a repository secret
  like this (replace the token):

```bash
kubectl -n argocd create secret generic repo-portfolio \
  --from-literal=type=git \
  --from-literal=url=https://github.com/byrmsh/portfolio.git \
  --from-literal=username=git \
  --from-literal=password=ghp_REPLACE_ME \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n argocd label secret repo-portfolio argocd.argoproj.io/secret-type=repository --overwrite
```

- Secrets are intentionally not managed by the chart. Create/update them
  separately in the `portfolio` namespace (same as today).

## Production (k3s / Homelab)

Recommended model:

- Keep *cluster bootstrapping* in your `homelab/` repo (Pulumi provisions k3s,
  installs Argo CD, and applies a single "root" Application).
- Keep *application release payload* in the app repo (this repo): Helm chart +
  values.

This repo includes a starting `Application` that targets `values-prod.yaml`:

- `deploy/argocd/applications/portfolio-prod.yaml`

In practice you usually apply that manifest from the *GitOps root* repo (often
`homelab/`), so the cluster state lives in one place.
