#!/usr/bin/env bash
set -euo pipefail

with_upworker=false
with_upworkerbot=false

while [ $# -gt 0 ]; do
  case "$1" in
    --with-upworker)
      with_upworker=true
      shift
      ;;
    --with-upworkerbot)
      with_upworkerbot=true
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: k8s-local-apply.sh [--with-upworker] [--with-upworkerbot]

Builds local images, loads them into minikube, and deploys the Helm release.

By default, this builds the core images (api, web, collector, ankiworker, lyricist).
Upwork components are opt-in because they require secrets.
EOF
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

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

echo "[1/8] Building local images..."
docker build -f apps/api/Dockerfile -t portfolio-api:dev .
docker build -f apps/web/Dockerfile -t portfolio-web:dev .
docker build -f apps/collector/Dockerfile -t portfolio-collector:dev .
docker build -f apps/ankiworker/Dockerfile -t portfolio-ankiworker:dev .
docker build -f apps/lyricist/Dockerfile -t portfolio-lyricist:dev .
if [ "${with_upworker}" = "true" ]; then
  docker build -f apps/upworker/Dockerfile -t portfolio-upworker:dev .
fi
if [ "${with_upworkerbot}" = "true" ]; then
  docker build -f apps/upworkerbot/Dockerfile -t portfolio-upworkerbot:dev .
fi

echo "[2/8] Loading images into minikube..."
minikube image load --overwrite=true portfolio-api:dev
echo "Loaded portfolio-api:dev into minikube"
minikube image load --overwrite=true portfolio-web:dev
echo "Loaded portfolio-web:dev into minikube"
minikube image load --overwrite=true portfolio-collector:dev
echo "Loaded portfolio-collector:dev into minikube"
minikube image load --overwrite=true portfolio-ankiworker:dev
echo "Loaded portfolio-ankiworker:dev into minikube"
minikube image load --overwrite=true portfolio-lyricist:dev
echo "Loaded portfolio-lyricist:dev into minikube"
if [ "${with_upworker}" = "true" ]; then
  minikube image load --overwrite=true portfolio-upworker:dev
  echo "Loaded portfolio-upworker:dev into minikube"
fi
if [ "${with_upworkerbot}" = "true" ]; then
  minikube image load --overwrite=true portfolio-upworkerbot:dev
  echo "Loaded portfolio-upworkerbot:dev into minikube"
fi

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required. Install Helm to deploy ./deploy/helm/portfolio." >&2
  exit 1
fi

echo "[3/8] Deploying Helm release..."
helm upgrade --install portfolio ./deploy/helm/portfolio \
  --namespace portfolio \
  --create-namespace \
  --reset-values

restart_deploy_if_exists() {
  local name="$1"
  if kubectl -n portfolio get deploy "$name" >/dev/null 2>&1; then
    kubectl -n portfolio rollout restart "deploy/$name"
  fi
}

rollout_status_if_exists() {
  local name="$1"
  if kubectl -n portfolio get deploy "$name" >/dev/null 2>&1; then
    kubectl -n portfolio rollout status "deploy/$name" --timeout=300s
  fi
}

echo "[3.5/8] Restarting workloads to pick up refreshed :dev images..."
restart_deploy_if_exists api-deployment
restart_deploy_if_exists web-deployment
restart_deploy_if_exists upworker-deployment
restart_deploy_if_exists upworker-bot-deployment

echo "[4/8] Waiting for db rollout..."
rollout_status_if_exists db-deployment

echo "[5/8] Waiting for api rollout..."
rollout_status_if_exists api-deployment

echo "[6/8] Waiting for web rollout..."
rollout_status_if_exists web-deployment

echo "[7/8] Waiting for upworker rollout (if enabled)..."
rollout_status_if_exists upworker-deployment

echo "[8/8] Waiting for upworker-bot rollout (if enabled)..."
rollout_status_if_exists upworker-bot-deployment

echo "Local apply completed."
