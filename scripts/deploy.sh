#!/usr/bin/env bash
# Pixelle-Video production deploy script.
# Usage: IMAGE_TAG=dev-abc123 ./scripts/deploy.sh
set -euo pipefail

LOCK_FILE="/tmp/pixelle-video-deploy.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "==> Another deploy is running, skip this trigger"
  exit 0
fi

cd "$(dirname "$0")/.."

set -a
if [ -f .env ]; then
  # shellcheck disable=SC1091
  source .env
else
  echo "==> .env not found, using environment/default values"
fi
set +a

TAG="${IMAGE_TAG:-latest}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
REGISTRY="${REGISTRY:?REGISTRY is required. Copy .env.example to .env and configure REGISTRY.}"
WEB_PORT="${WEB_PORT:-8080}"
API_PORT="${API_PORT:-8000}"

export IMAGE_TAG="$TAG"
export GIT_COMMIT="${GIT_COMMIT:-$(git rev-parse HEAD 2>/dev/null || echo unknown)}"
export BUILD_TIME="${BUILD_TIME:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose -f "$COMPOSE_FILE" "$@"
  else
    docker-compose -f "$COMPOSE_FILE" "$@"
  fi
}

feishu_notify() {
  local title="$1" color="$2" body="$3"
  [ -z "${FEISHU_WEBHOOK_URL:-}" ] && return 0
  curl -sf -X POST "$FEISHU_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "{\"msg_type\":\"interactive\",\"card\":{\"header\":{\"title\":{\"content\":\"$title\",\"tag\":\"plain_text\"},\"template\":\"$color\"},\"elements\":[{\"tag\":\"div\",\"text\":{\"content\":\"$body\",\"tag\":\"lark_md\"}}]}}" \
    >/dev/null 2>&1 || true
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

HANDLED_FAILURE=false
handle_error() {
  [ "$HANDLED_FAILURE" = "true" ] && return
  HANDLED_FAILURE=true
  echo "==> Deploy failed, sending notification"
  feishu_notify "❌ Pixelle-Video 部署失败" "red" "**Tag**: $TAG\n**Commit**: ${GIT_COMMIT:-unknown}\n**时间**: $(date '+%Y-%m-%d %H:%M:%S')\n请检查服务器日志"
}
trap handle_error ERR

echo "==> Deploying Pixelle-Video tag: $TAG"
echo "==> Registry: $REGISTRY"

if [ -n "${ACR_USERNAME:-}" ] && [ -n "${ACR_PASSWORD:-}" ]; then
  REGISTRY_HOST="${REGISTRY%%/*}"
  echo "$ACR_PASSWORD" | docker login "$REGISTRY_HOST" -u "$ACR_USERNAME" --password-stdin
  echo "==> ACR login OK"
fi

if [ "${PIXELLE_SKIP_PULL:-false}" != "true" ]; then
  echo "==> Pulling images..."
  compose pull api web
else
  echo "==> PIXELLE_SKIP_PULL=true, skip docker pull"
fi

echo "==> Starting services..."
compose up -d --remove-orphans

echo "==> Waiting for API health..."
if ! health_check "http://127.0.0.1:${API_PORT}/health" "api"; then
  echo "==> API health check failed"
  ./scripts/rollback.sh || true
  HANDLED_FAILURE=true
  feishu_notify "❌ Pixelle-Video 部署失败，已尝试回滚" "red" "**失败 Tag**: $TAG\n**Commit**: ${GIT_COMMIT:-unknown}\nAPI 健康检查失败"
  exit 1
fi

echo "==> Waiting for Web health..."
if ! health_check "http://127.0.0.1:${WEB_PORT}/health" "web"; then
  echo "==> Web health check failed"
  ./scripts/rollback.sh || true
  HANDLED_FAILURE=true
  feishu_notify "❌ Pixelle-Video 部署失败，已尝试回滚" "red" "**失败 Tag**: $TAG\n**Commit**: ${GIT_COMMIT:-unknown}\nWeb 健康检查失败"
  exit 1
fi

echo "$TAG" > .last_good_tag
echo "==> Deploy OK ($TAG)"
feishu_notify "✅ Pixelle-Video 部署成功" "green" "**Tag**: $TAG\n**Commit**: ${GIT_COMMIT:-unknown}\n**时间**: ${BUILD_TIME:-unknown}\n健康检查通过"
