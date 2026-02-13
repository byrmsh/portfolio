#!/usr/bin/env bash
set -euo pipefail

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required." >&2
  exit 1
fi

if ! command -v minikube >/dev/null 2>&1; then
  echo "minikube is required for this bootstrap helper." >&2
  exit 1
fi

if ! minikube status >/dev/null 2>&1; then
  echo "minikube does not look running. Start it first: minikube start" >&2
  exit 1
fi

echo "[1/4] Installing Argo CD (argocd namespace)..."
kubectl get ns argocd >/dev/null 2>&1 || kubectl create namespace argocd

# Use server-side apply to avoid the oversized last-applied-configuration annotation
# on large CRDs (common on Argo CD installs).
#
# If you previously installed Argo CD with client-side apply, server-side apply
# may hit manager conflicts. For local bootstrap, it's reasonable to force
# conflicts to converge the install manifest under a single manager.
install_url="https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml"
field_manager="codex-argocd-bootstrap"

set +e
kubectl -n argocd apply --server-side=true --field-manager="${field_manager}" -f "${install_url}"
rc=$?
set -e

if [ "${rc}" -ne 0 ]; then
  echo "Argo CD apply hit SSA conflicts (likely from a previous client-side install). Retrying with --force-conflicts..."
  kubectl -n argocd apply --server-side=true --force-conflicts --field-manager="${field_manager}" -f "${install_url}"
fi

echo "[2/4] Waiting for Argo CD server to be ready..."
kubectl -n argocd rollout status deploy/argocd-redis --timeout=300s
kubectl -n argocd rollout status deploy/argocd-repo-server --timeout=300s
kubectl -n argocd rollout status deploy/argocd-server --timeout=300s

# The initial admin secret is only created once the server initializes.
for _ in $(seq 1 60); do
  if kubectl -n argocd get secret argocd-initial-admin-secret >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "[3/4] Applying portfolio Argo CD Application (local)..."
kubectl -n argocd apply -f deploy/argocd/applications/portfolio-local.yaml

echo "[4/4] Next steps:"
echo "- Port-forward Argo CD UI:"
echo "    kubectl -n argocd port-forward svc/argocd-server 8088:443"
echo "- Get initial admin password:"
echo "    kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo"
echo "- UI: https://localhost:8088 (user: admin)"
echo
echo "If the repo is private, add repo credentials in Argo CD before syncing."
