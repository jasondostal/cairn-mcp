#!/usr/bin/env bash
set -euo pipefail

# Deploy cairn to a remote host
#
# Flow: build locally → docker save → scp → docker load on remote → up
# Skips the GHCR round-trip for faster deploys.
#
# Usage:
#   DEPLOY_HOST=myserver DEPLOY_COMPOSE_DIR=/path/to/compose ./scripts/deploy.sh
#   ./scripts/deploy.sh --skip-build  # deploy existing :local images

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOY_HOST="${DEPLOY_HOST:?Set DEPLOY_HOST to your remote hostname}"
DEPLOY_COMPOSE_DIR="${DEPLOY_COMPOSE_DIR:?Set DEPLOY_COMPOSE_DIR to the remote docker compose directory}"
TMP_DIR="/tmp/cairn-deploy"

SKIP_BUILD=false
if [ "${1:-}" = "--skip-build" ]; then
  SKIP_BUILD=true
fi

echo "=== Deploying cairn to ${DEPLOY_HOST} ==="

# --- Build locally ---
if [ "$SKIP_BUILD" = false ]; then
  echo "Building images..."
  docker build -t cairn-mcp:local "$REPO_DIR"
  docker build -t cairn-mcp-ui:local "$REPO_DIR/cairn-ui"
  echo "Build complete."
else
  echo "Skipping build (--skip-build)."
  # Verify images exist
  docker image inspect cairn-mcp:local >/dev/null 2>&1 || { echo "ERROR: cairn-mcp:local not found. Build first."; exit 1; }
  docker image inspect cairn-mcp-ui:local >/dev/null 2>&1 || { echo "ERROR: cairn-mcp-ui:local not found. Build first."; exit 1; }
fi

# --- Transfer to remote ---
echo "Saving images..."
mkdir -p "$TMP_DIR"
docker save cairn-mcp:local cairn-mcp-ui:local | gzip > "$TMP_DIR/cairn-images.tar.gz"

echo "Transferring to ${DEPLOY_HOST} (~$(du -h "$TMP_DIR/cairn-images.tar.gz" | cut -f1))..."
scp "$TMP_DIR/cairn-images.tar.gz" "$DEPLOY_HOST:/tmp/cairn-images.tar.gz"

echo "Loading images on ${DEPLOY_HOST}..."
ssh "$DEPLOY_HOST" "gunzip -c /tmp/cairn-images.tar.gz | docker load && rm /tmp/cairn-images.tar.gz"

# --- Deploy on remote ---
echo "Restarting services (--no-deps: NEVER recreate cairn-db)..."
ssh "$DEPLOY_HOST" "cd $DEPLOY_COMPOSE_DIR && docker compose up -d --no-deps cairn cairn-ui"

# --- Health check ---
echo "Waiting for cairn to be healthy..."
timeout=90
elapsed=0
while [ $elapsed -lt $timeout ]; do
  status=$(ssh "$DEPLOY_HOST" "docker inspect --format='{{.State.Health.Status}}' cairn 2>/dev/null" || echo "unknown")
  if [ "$status" = "healthy" ]; then
    break
  fi
  sleep 3
  elapsed=$((elapsed + 3))
done

if [ $elapsed -ge $timeout ]; then
  echo "ERROR: cairn did not become healthy within ${timeout}s"
  ssh "$DEPLOY_HOST" "docker logs cairn --tail 20"
  exit 1
fi

echo "cairn is healthy."

# --- Smoke test ---
if [ -x "$SCRIPT_DIR/smoke-test.sh" ]; then
  echo "Running smoke test..."
  "$SCRIPT_DIR/smoke-test.sh" "${DEPLOY_HOST}:8000"
else
  echo "Smoke test script not found, skipping."
fi

# --- Cleanup ---
rm -rf "$TMP_DIR"

echo "=== Deploy complete ==="
