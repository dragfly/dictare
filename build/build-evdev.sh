#!/bin/bash
# Build evdev wheel using Docker (no python3-dev needed on host)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Clean old wheels
rm -f evdev-*.whl evdev.whl

echo "Building evdev wheel in Docker..."
docker build -q -f Dockerfile.evdev -t evdev-builder . >/dev/null

echo "Extracting wheel..."
docker run --rm -v "$SCRIPT_DIR:/output" evdev-builder

WHEEL=$(ls evdev-*.whl 2>/dev/null | head -1)
if [ -z "$WHEEL" ]; then
    echo "Error: No wheel file found"
    exit 1
fi

echo ""
echo "Build complete!"
ls -la "$WHEEL"

echo ""
echo "To install:"
echo "  uv pip install build/$WHEEL"
