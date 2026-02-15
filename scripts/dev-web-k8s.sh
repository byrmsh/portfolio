#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${K8S_NAMESPACE:-portfolio}"
API_SERVICE="${K8S_API_SERVICE:-api-service}"
API_PORT="${K8S_API_PORT:-3000}"
LOCAL_PORT="${API_LOCAL_PORT:-3000}"
API_ORIGIN="${API_ORIGIN:-http://127.0.0.1:${LOCAL_PORT}}"
K8S_CONTEXT="${K8S_CONTEXT:-}"

is_local_context_name() {
  case "$1" in
    minikube|minikube-*) return 0 ;;
    kind|kind-*) return 0 ;;
    docker-desktop) return 0 ;;
    *) return 1 ;;
  esac
}

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required." >&2
  exit 1
fi

CTX="${K8S_CONTEXT:-$(kubectl config current-context 2>/dev/null || true)}"
if [ -z "${CTX}" ]; then
  echo "kubectl has no current context configured." >&2
  exit 1
fi
if [ -n "${K8S_CONTEXT}" ] || is_local_context_name "${CTX}"; then
  :
else
  echo "Refusing to run pnpm dev against non-local kubectl context: ${CTX}" >&2
  echo "Switch to your local cluster (e.g. kubectx minikube) or set K8S_CONTEXT=your-local-context." >&2
  exit 1
fi

if ! kubectl --context "${CTX}" version --request-timeout=5s >/dev/null 2>&1; then
  echo "Kubernetes cluster is unreachable." >&2
  echo "If you use minikube, start it first: minikube start" >&2
  exit 1
fi

if ! kubectl --context "${CTX}" -n "${NAMESPACE}" get svc "${API_SERVICE}" >/dev/null 2>&1; then
  echo "Service ${API_SERVICE} not found in namespace ${NAMESPACE}; bootstrapping local workloads..." >&2
  pnpm k8s:local:apply
fi

if ! kubectl --context "${CTX}" -n "${NAMESPACE}" get svc "${API_SERVICE}" >/dev/null 2>&1; then
  echo "Service ${API_SERVICE} is still missing in namespace ${NAMESPACE} after bootstrap." >&2
  exit 1
fi

echo "Starting port-forward ${NAMESPACE}/${API_SERVICE} ${LOCAL_PORT}:${API_PORT}..."
kubectl --context "${CTX}" -n "${NAMESPACE}" port-forward "svc/${API_SERVICE}" "${LOCAL_PORT}:${API_PORT}" >/tmp/portfolio-api-port-forward.log 2>&1 &
PF_PID=$!

cleanup() {
  if kill -0 "${PF_PID}" >/dev/null 2>&1; then
    kill "${PF_PID}" >/dev/null 2>&1 || true
    wait "${PF_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# Wait until API responds or timeout.
for _ in $(seq 1 30); do
  if curl -fsS "${API_ORIGIN}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.3
done

if ! curl -fsS "${API_ORIGIN}/health" >/dev/null 2>&1; then
  echo "Port-forward started but API health check failed at ${API_ORIGIN}/health." >&2
  echo "Port-forward logs: /tmp/portfolio-api-port-forward.log" >&2
  exit 1
fi

echo "API available at ${API_ORIGIN}; starting web dev server..."
jobs_probe="$(curl -fsS "${API_ORIGIN}/api/jobs?limit=1" 2>/dev/null || true)"
if echo "${jobs_probe}" | grep -q '"source":"redis"'; then
  echo "Detected stale API (jobs endpoint still backed by Redis). Refreshing local api image + deployment..." >&2
  cleanup
  pnpm k8s:local:api

  echo "Restarting port-forward ${NAMESPACE}/${API_SERVICE} ${LOCAL_PORT}:${API_PORT}..." >&2
  kubectl --context "${CTX}" -n "${NAMESPACE}" port-forward "svc/${API_SERVICE}" "${LOCAL_PORT}:${API_PORT}" >/tmp/portfolio-api-port-forward.log 2>&1 &
  PF_PID=$!
  trap cleanup EXIT INT TERM

  for _ in $(seq 1 30); do
    if curl -fsS "${API_ORIGIN}/health" >/dev/null 2>&1; then
      break
    fi
    sleep 0.3
  done
fi

API_ORIGIN="${API_ORIGIN}" pnpm -C apps/web dev "$@"
