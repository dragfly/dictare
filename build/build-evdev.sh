#!/bin/bash
# Build evdev wheel using Docker (no python3-dev needed on host)
# Produces: evdev-*.whl

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Building evdev wheel in Docker..."
docker build -f Dockerfile.evdev -t evdev-builder .

echo "Extracting wheel..."
docker run --rm evdev-builder > evdev.whl

echo ""
echo "Build complete!"
ls -la evdev.whl

echo ""
echo "To install:"
echo "  uv pip install build/evdev.whl"
