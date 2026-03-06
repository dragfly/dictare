#!/usr/bin/env bash
# Install or upgrade dictare. Auto-detects platform.
#
# Usage:
#   ./scripts/install.sh                  # install current version
#   ./scripts/install.sh --version v0.1.130  # install specific version (rollback)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VERSION=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) VERSION="$2"; shift 2 ;;
        *) break ;;
    esac
done

# Rollback: checkout the requested version before installing
if [[ -n "$VERSION" ]]; then
    echo "==> Rolling back to ${VERSION}..."
    git -C "$PROJECT_DIR" fetch --tags
    git -C "$PROJECT_DIR" checkout "$VERSION" -- .
    echo "==> Checked out ${VERSION}, running its installer..."
fi

case "$(uname -s)" in
    Darwin) exec "${SCRIPT_DIR}/macos/install.sh" "$@" ;;
    Linux)  exec "${SCRIPT_DIR}/linux/install.sh" "$@" ;;
    *)      echo "ERROR: unsupported platform $(uname -s)" >&2; exit 1 ;;
esac
