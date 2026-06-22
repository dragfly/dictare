#!/usr/bin/env bash
# Development entrypoint for the same installer users run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

exec "$PROJECT_DIR/install.sh" "$@"
