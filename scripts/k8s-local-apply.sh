#!/usr/bin/env bash
set -euo pipefail

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required." >&2
  exit 1
fi

echo "[1/6] Building local images..."
docker build -f apps/api/Dockerfile -t portfolio-api:dev .
docker build -f apps/web/Dockerfile -t portfolio-web:dev .
docker build -f apps/collector/Dockerfile -t portfolio-collector:dev .
docker build -f apps/ankiworker/Dockerfile -t portfolio-ankiworker:dev .
docker build -f apps/lyricist/Dockerfile -t portfolio-lyricist:dev .

echo "[2/6] Loading images into minikube..."
minikube image load portfolio-api:dev
minikube image load portfolio-web:dev
minikube image load portfolio-collector:dev
minikube image load portfolio-ankiworker:dev
minikube image load portfolio-lyricist:dev

echo "[3/6] Deploying Helm release..."
helm upgrade --install portfolio ./deploy/helm/portfolio \
  --namespace portfolio \
  --create-namespace

echo "[4/6] Waiting for db rollout..."
kubectl -n portfolio rollout status deploy/db-deployment

echo "[5/6] Waiting for api rollout..."
kubectl -n portfolio rollout status deploy/api-deployment

echo "[6/6] Waiting for web rollout..."
kubectl -n portfolio rollout status deploy/web-deployment

echo "Local apply completed."
