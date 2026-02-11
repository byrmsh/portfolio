#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${K8S_NAMESPACE:-portfolio}"
API_SERVICE="${K8S_API_SERVICE:-api-service}"
API_PORT="${K8S_API_PORT:-3000}"
LOCAL_PORT="${API_LOCAL_PORT:-3000}"
API_ORIGIN="${API_ORIGIN:-http://127.0.0.1:${LOCAL_PORT}}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required." >&2
  exit 1
fi

if ! kubectl -n "${NAMESPACE}" get svc "${API_SERVICE}" >/dev/null 2>&1; then
  echo "Service ${API_SERVICE} not found in namespace ${NAMESPACE}." >&2
  echo "Run: pnpm k8s:local:apply" >&2
  exit 1
fi

echo "Starting port-forward ${NAMESPACE}/${API_SERVICE} ${LOCAL_PORT}:${API_PORT}..."
kubectl -n "${NAMESPACE}" port-forward "svc/${API_SERVICE}" "${LOCAL_PORT}:${API_PORT}" >/tmp/portfolio-api-port-forward.log 2>&1 &
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
API_ORIGIN="${API_ORIGIN}" pnpm -C apps/web dev "$@"
