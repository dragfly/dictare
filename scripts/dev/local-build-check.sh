#!/usr/bin/env bash
# Local build check - runs the same checks as CI/CD pipeline
# Run this before bump to ensure build will pass

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_DIR"

echo "=== Local Build Check ==="
echo ""

# Step 1: Sync dependencies
echo "[1/4] Syncing dependencies..."
uv sync --python 3.11 --prerelease=allow --extra dev --quiet

# Step 2: Lint
echo "[2/4] Running ruff..."
.venv/bin/ruff check src/

# Step 3: Type check
echo "[3/4] Running mypy..."
.venv/bin/mypy src/

# Step 4: Tests
echo "[4/4] Running tests..."
.venv/bin/pytest tests/ -q

echo ""
echo "=== All checks passed ==="
