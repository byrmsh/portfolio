#!/usr/bin/env bash
set -euo pipefail

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required." >&2
  exit 1
fi

if ! command -v minikube >/dev/null 2>&1; then
  echo "minikube is required." >&2
  exit 1
fi

CTX="${K8S_CONTEXT:-$(kubectl config current-context 2>/dev/null || true)}"
if [ -z "${CTX}" ]; then
  echo "kubectl has no current context configured." >&2
  exit 1
fi

echo "[1/4] Building web image..."
docker build -f apps/web/Dockerfile -t portfolio-web:dev .

echo "[2/4] Loading image into minikube..."
minikube image load --overwrite=true portfolio-web:dev

echo "[3/4] Restarting web deployment..."
kubectl --context "${CTX}" -n portfolio rollout restart deployment/web-deployment

echo "[4/4] Waiting for rollout..."
kubectl --context "${CTX}" -n portfolio rollout status deploy/web-deployment

echo "Web update completed."
