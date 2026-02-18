#!/usr/bin/env bash
# Tray test: start tray app with virtual display
set -euo pipefail

echo "=== TRAY TEST ==="

# Start Xvfb (virtual display)
echo "1. Starting Xvfb..."
Xvfb :99 -screen 0 1024x768x24 &
XVFB_PID=$!
export DISPLAY=:99

# Start dbus session
echo "2. Starting dbus session..."
eval $(dbus-launch --sh-syntax)

TRAY_PID=""

# Cleanup on exit
cleanup() {
    echo "Cleaning up..."
    [[ -n "$TRAY_PID" ]] && kill $TRAY_PID 2>/dev/null || true
    kill $XVFB_PID 2>/dev/null || true
    kill $DBUS_SESSION_BUS_PID 2>/dev/null || true
}
trap cleanup EXIT

# Wait for Xvfb to be ready
sleep 1

# Start tray app in background (standalone mode, no engine connection)
echo "3. Starting tray app..."
python -m voxtype tray &
TRAY_PID=$!

# Give it time to initialize
echo "4. Waiting for tray to initialize..."
sleep 3

# Check if process is still running
if kill -0 $TRAY_PID 2>/dev/null; then
    echo "   Tray process running (PID $TRAY_PID)"
else
    echo "ERROR: Tray process died"
    exit 1
fi

echo "=== TRAY TEST PASSED ==="
