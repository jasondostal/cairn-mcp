#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
  echo "Usage: ./scripts/release.sh <version>"
  echo "Example: ./scripts/release.sh 0.41.0"
  exit 1
fi

# Validate format (major.minor.patch)
if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "ERROR: Version must be in semver format (e.g. 0.41.0)"
  exit 1
fi

# Check we're on main
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ]; then
  echo "ERROR: Must be on main branch (currently on '$BRANCH')"
  exit 1
fi

# Check for uncommitted changes
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: Working tree has uncommitted changes. Commit or stash first."
  exit 1
fi

# Verify version was bumped in source files
INIT_VERSION=$(grep '__version__' cairn/__init__.py | sed 's/.*"\(.*\)".*/\1/')
PYPROJECT_VERSION=$(grep '^version' pyproject.toml | sed 's/.*"\(.*\)".*/\1/')
UI_VERSION=$(grep '"version"' cairn-ui/package.json | sed 's/.*"\([0-9][^"]*\)".*/\1/')

if [ "$INIT_VERSION" != "$VERSION" ]; then
  echo "ERROR: cairn/__init__.py has version '$INIT_VERSION', expected '$VERSION'"
  echo "  Bump version before running release.sh"
  exit 1
fi

if [ "$PYPROJECT_VERSION" != "$VERSION" ]; then
  echo "ERROR: pyproject.toml has version '$PYPROJECT_VERSION', expected '$VERSION'"
  exit 1
fi

if [ "$UI_VERSION" != "$VERSION" ]; then
  echo "ERROR: cairn-ui/package.json has version '$UI_VERSION', expected '$VERSION'"
  exit 1
fi

# Verify CHANGELOG has an entry for this version
if ! grep -q "\[$VERSION\]" CHANGELOG.md; then
  echo "ERROR: No CHANGELOG.md entry found for [$VERSION]"
  exit 1
fi

echo "=== Releasing v$VERSION ==="
echo "  cairn/__init__.py:      $INIT_VERSION"
echo "  pyproject.toml:         $PYPROJECT_VERSION"
echo "  cairn-ui/package.json:  $UI_VERSION"
echo "  CHANGELOG.md:           found"
echo ""

# Tag and push
git tag "v$VERSION"
echo "Tagged v$VERSION"

git push
git push --tags
echo "Pushed to origin"

echo ""
echo "=== v$VERSION released ==="
echo "CI will build images. Then deploy with:"
echo "  ./scripts/deploy.sh $VERSION"
