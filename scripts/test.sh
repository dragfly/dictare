#!/usr/bin/env bash
# Run dictare tests.
# Usage:
#   ./scripts/test.sh          # fast tests only (~8s)
#   ./scripts/test.sh --full   # all tests including slow (~19s)
set -euo pipefail

ARGS=(-x --tb=short -q)

if [[ "${1:-}" == "--full" ]]; then
    echo "==> Running all tests (fast + slow)..."
else
    echo "==> Running fast tests..."
    ARGS+=(-m "not slow")
fi

uv run --python 3.11 pytest tests/ "${ARGS[@]}"
