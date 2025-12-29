#!/bin/bash
# Build ydotool from source using Docker
# Produces: ydotool and ydotoold binaries

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Building ydotool in Docker..."
docker build -f Dockerfile.ydotool -t ydotool-builder .

echo "Extracting binaries..."
docker run --rm ydotool-builder cat /ydotool > ydotool
docker run --rm ydotool-builder cat /ydotoold > ydotoold

chmod +x ydotool ydotoold

echo ""
echo "Build complete! Binaries:"
ls -la ydotool ydotoold

echo ""
echo "To install system-wide:"
echo "  sudo mv ydotool ydotoold /usr/local/bin/"
echo ""
echo "To start the daemon:"
echo "  sudo ydotoold &"
echo ""
echo "Or create a systemd service (see README)"
