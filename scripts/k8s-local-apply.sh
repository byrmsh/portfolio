#!/usr/bin/env bash
set -euo pipefail

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required." >&2
  exit 1
fi

echo "[1/8] Building local images..."
docker build -f apps/api/Dockerfile -t portfolio-api:dev .
docker build -f apps/web/Dockerfile -t portfolio-web:dev .
docker build -f apps/collector/Dockerfile -t portfolio-collector:dev .
docker build -f apps/ankiworker/Dockerfile -t portfolio-ankiworker:dev .
docker build -f apps/lyricist/Dockerfile -t portfolio-lyricist:dev .
docker build -f apps/upworker/Dockerfile -t portfolio-upworker:dev .
docker build -f apps/upworkerbot/Dockerfile -t portfolio-upworkerbot:dev .

echo "[2/8] Loading images into minikube..."
minikube image load portfolio-api:dev
minikube image load portfolio-web:dev
minikube image load portfolio-collector:dev
minikube image load portfolio-ankiworker:dev
minikube image load portfolio-lyricist:dev
minikube image load portfolio-upworker:dev
minikube image load portfolio-upworkerbot:dev

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required. Install Helm to deploy ./deploy/helm/portfolio." >&2
  exit 1
fi

echo "[3/8] Deploying Helm release..."
helm upgrade --install portfolio ./deploy/helm/portfolio \
  --namespace portfolio \
  --create-namespace \
  --set upworker.enabled=true \
  --set upworkerBot.enabled=true

echo "[4/8] Waiting for db rollout..."
kubectl -n portfolio rollout status deploy/db-deployment

echo "[5/8] Waiting for api rollout..."
kubectl -n portfolio rollout status deploy/api-deployment

echo "[6/8] Waiting for web rollout..."
kubectl -n portfolio rollout status deploy/web-deployment

echo "[7/8] Waiting for upworker rollout..."
kubectl -n portfolio rollout status deploy/upworker-deployment

echo "[8/8] Waiting for upworker-bot rollout..."
kubectl -n portfolio rollout status deploy/upworker-bot-deployment

echo "Local apply completed."
