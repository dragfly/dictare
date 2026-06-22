#!/usr/bin/env bash
# Build the current working tree and install it through the product runtime store.
#
# This intentionally does not edit the Homebrew tap. Development installs and
# user installs should exercise the same Dictare-owned lifecycle.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
DIST_DIR="$PROJECT_DIR/dist"

cd "$PROJECT_DIR"

VERSION=$(grep -E '^__version__' src/dictare/__init__.py | sed 's/.*"\(.*\)"/\1/')
TARBALL="$DIST_DIR/dictare-${VERSION}.tar.gz"

echo "==> Building dictare ${VERSION}"
uv build --sdist --quiet

if [[ ! -f "$TARBALL" ]]; then
    echo "ERROR: expected tarball not found: $TARBALL" >&2
    exit 1
fi

echo "==> Installing from local artifact"
exec "$PROJECT_DIR/install.sh" --from-path "$TARBALL" --version "$VERSION" "$@"
