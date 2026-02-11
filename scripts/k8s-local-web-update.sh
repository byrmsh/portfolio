#!/usr/bin/env bash
set -euo pipefail

echo "[1/4] Building web image..."
docker build -f apps/web/Dockerfile -t portfolio-web:dev .

echo "[2/4] Loading image into minikube..."
minikube image load portfolio-web:dev

echo "[3/4] Restarting web deployment..."
kubectl -n portfolio rollout restart deployment/web-deployment

echo "[4/4] Waiting for rollout..."
kubectl -n portfolio rollout status deploy/web-deployment

echo "Web update completed."
