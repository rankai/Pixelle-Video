#!/usr/bin/env bash
# Pixelle-Video rollback script.
set -euo pipefail

cd "$(dirname "$0")/.."

set -a
if [ -f .env ]; then
  # shellcheck disable=SC1091
  source .env
fi
set +a

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
REGISTRY="${REGISTRY:?REGISTRY is required. Copy .env.example to .env and configure REGISTRY.}"
WEB_PORT="${WEB_PORT:-18080}"
API_PORT="${API_PORT:-8000}"

if [ ! -f .last_good_tag ]; then
  echo "==> .last_good_tag not found, cannot rollback"
  exit 1
fi

ROLLBACK_TAG="$(cat .last_good_tag)"
if [ -z "$ROLLBACK_TAG" ]; then
  echo "==> .last_good_tag is empty, cannot rollback"
  exit 1
fi

export IMAGE_TAG="$ROLLBACK_TAG"

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose -f "$COMPOSE_FILE" "$@"
  else
    docker-compose -f "$COMPOSE_FILE" "$@"
  fi
}

health_check() {
  local url="$1"
  local label="$2"
  for i in $(seq 1 20); do
    if curl -sf "$url" >/dev/null 2>&1; then
      echo "    $label ready"
      return 0
    fi
    echo "    $label retry $i/20..."
    sleep 3
  done
  return 1
}

echo "==> Rolling back Pixelle-Video to tag: $ROLLBACK_TAG"

if [ -n "${ACR_USERNAME:-}" ] && [ -n "${ACR_PASSWORD:-}" ]; then
  REGISTRY_HOST="${REGISTRY%%/*}"
  echo "$ACR_PASSWORD" | docker login "$REGISTRY_HOST" -u "$ACR_USERNAME" --password-stdin
fi

if [ "${PIXELLE_SKIP_PULL:-false}" != "true" ]; then
  compose pull api web
fi

compose up -d --remove-orphans

health_check "http://127.0.0.1:${API_PORT}/health" "api"
health_check "http://127.0.0.1:${WEB_PORT}/health" "web"

echo "==> Rollback OK ($ROLLBACK_TAG)"
