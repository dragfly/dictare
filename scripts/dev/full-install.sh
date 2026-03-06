#!/usr/bin/env bash
# Full dev install: build UI, update lock, install dictare.
#
# The openvip SDK is now on PyPI — no local repo needed.
# Use this when you've changed the UI or need a clean install.
# Use ./scripts/install.sh for a quick reinstall (no UI rebuild).
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ---------- 1. Build UI ----------
echo "==> Building UI..."
cd "${PROJECT_DIR}/ui"
pnpm install --frozen-lockfile --silent
pnpm run build

# ---------- 2. Update lock file ----------
echo "==> Updating uv.lock..."
cd "$PROJECT_DIR"
uv lock --python 3.11

# ---------- 3. Install ----------
echo "==> Installing dictare..."
exec "${SCRIPT_DIR}/install.sh"
