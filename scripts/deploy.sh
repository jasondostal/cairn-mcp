#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-latest}"
REGISTRY="ghcr.io/jasondostal"

echo "=== Deploying cairn $VERSION ==="

# Pull images
echo "Pulling images..."
docker pull "$REGISTRY/cairn-mcp:$VERSION"
docker pull "$REGISTRY/cairn-mcp-ui:$VERSION"

# Tag as :latest if deploying a specific version so compose picks it up
if [ "$VERSION" != "latest" ]; then
  docker tag "$REGISTRY/cairn-mcp:$VERSION" "$REGISTRY/cairn-mcp:latest"
  docker tag "$REGISTRY/cairn-mcp-ui:$VERSION" "$REGISTRY/cairn-mcp-ui:latest"
fi

# Restart services (--no-deps: NEVER recreate cairn-db, it has its own password/data)
echo "Restarting services..."
docker compose up -d --no-deps cairn cairn-ui

# Wait for health
echo "Waiting for cairn to be healthy..."
timeout=60
elapsed=0
while [ $elapsed -lt $timeout ]; do
  if docker inspect --format='{{.State.Health.Status}}' cairn 2>/dev/null | grep -q healthy; then
    break
  fi
  sleep 2
  elapsed=$((elapsed + 2))
done

if [ $elapsed -ge $timeout ]; then
  echo "ERROR: cairn did not become healthy within ${timeout}s"
  docker logs cairn --tail 20
  exit 1
fi

# Smoke test
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -x "$SCRIPT_DIR/smoke-test.sh" ]; then
  "$SCRIPT_DIR/smoke-test.sh" localhost:8000
else
  echo "Smoke test script not found, skipping."
fi

echo "=== Deploy complete ==="
