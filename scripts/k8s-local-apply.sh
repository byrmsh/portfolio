#!/usr/bin/env bash
set -euo pipefail

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)
      cat <<'EOF'
Usage: k8s-local-apply.sh

Builds local images, loads them into minikube, and deploys the Helm release.

By default, this builds the core images (api, web, collector, ankiworker, lyricist).
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

CTX="${K8S_CONTEXT:-$(kubectl config current-context 2>/dev/null || true)}"
if [ -z "${CTX}" ]; then
  echo "kubectl has no current context configured." >&2
  exit 1
fi

echo "[1/6] Building local images..."
docker build -f apps/api/Dockerfile -t portfolio-api:dev .
docker build -f apps/web/Dockerfile -t portfolio-web:dev .
docker build -f apps/collector/Dockerfile -t portfolio-collector:dev .
docker build -f apps/ankiworker/Dockerfile -t portfolio-ankiworker:dev .
docker build -f apps/lyricist/Dockerfile -t portfolio-lyricist:dev .

echo "[2/6] Loading images into minikube..."
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

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required. Install Helm to deploy ./deploy/helm/portfolio." >&2
  exit 1
fi

echo "[3/6] Deploying Helm release..."
helm upgrade --install portfolio ./deploy/helm/portfolio \
  --namespace portfolio \
  --create-namespace \
  --reset-values \
  --kube-context "${CTX}"

restart_deploy_if_exists() {
  local name="$1"
  if kubectl --context "${CTX}" -n portfolio get deploy "$name" >/dev/null 2>&1; then
    kubectl --context "${CTX}" -n portfolio rollout restart "deploy/$name"
  fi
}

rollout_status_if_exists() {
  local name="$1"
  if kubectl --context "${CTX}" -n portfolio get deploy "$name" >/dev/null 2>&1; then
    kubectl --context "${CTX}" -n portfolio rollout status "deploy/$name" --timeout=300s
  fi
}

echo "[3.5/6] Restarting workloads to pick up refreshed :dev images..."
restart_deploy_if_exists api-deployment
restart_deploy_if_exists web-deployment

echo "[4/6] Waiting for db rollout..."
rollout_status_if_exists db-deployment

echo "[5/6] Waiting for api rollout..."
rollout_status_if_exists api-deployment

echo "[6/6] Waiting for web rollout..."
rollout_status_if_exists web-deployment

echo "Local apply completed."
