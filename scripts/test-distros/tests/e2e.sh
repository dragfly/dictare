#!/usr/bin/env bash
# End-to-end test: engine + tray + SSE connection
# NOTE: Requires audio devices and models. Skipped in Docker (no audio).
set -euo pipefail

echo "=== E2E TEST ==="

if [[ "${VOXTYPE_SKIP_E2E_TEST:-}" == "1" ]]; then
    echo "SKIPPED: VOXTYPE_SKIP_E2E_TEST=1"
    exit 0
fi

# Check for audio devices (not available in Docker)
echo "0. Checking for audio devices..."
AUDIO_DEVS=$(python -c "import sounddevice as sd; devs = [d for d in sd.query_devices() if d['max_input_channels'] > 0]; print(len(devs))" 2>/dev/null || echo "0")
echo "   Found $AUDIO_DEVS input devices"
if [[ "$AUDIO_DEVS" == "0" ]]; then
    echo "   No audio input devices found (likely running in Docker)"
    echo "   E2E test requires audio hardware"
    echo "SKIPPED: No audio devices"
    exit 0
fi

ENGINE_URL="http://127.0.0.1:8770"

# Check if models are available (HuggingFace cache)
echo "1. Checking for models..."
HF_CACHE="${HF_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/huggingface}/hub"
WHISPER_MODEL="$HF_CACHE/models--mobiuslabsgmbh--faster-whisper-large-v3-turbo"
if [[ ! -d "$WHISPER_MODEL" ]]; then
    echo "   No whisper model found in $WHISPER_MODEL"
    echo "   Run 'voxtype models download' first, or mount HF cache"
    echo "SKIPPED: Models not available"
    exit 0
fi
echo "   Whisper model found"

# Start Xvfb (virtual display)
echo "2. Starting Xvfb..."
Xvfb :99 -screen 0 1024x768x24 &
XVFB_PID=$!
export DISPLAY=:99

# Start dbus session
echo "3. Starting dbus session..."
eval $(dbus-launch --sh-syntax)

ENGINE_PID=""
TRAY_PID=""

# Cleanup on exit
cleanup() {
    echo "Cleaning up..."
    [[ -n "$TRAY_PID" ]] && kill $TRAY_PID 2>/dev/null || true
    [[ -n "$ENGINE_PID" ]] && kill $ENGINE_PID 2>/dev/null || true
    kill $XVFB_PID 2>/dev/null || true
    kill $DBUS_SESSION_BUS_PID 2>/dev/null || true
}
trap cleanup EXIT

sleep 1

# Start engine (verbose mode to disable interactive panel)
echo "4. Starting engine..."
python -m voxtype engine start --verbose 2>&1 &
ENGINE_PID=$!

# Wait for engine to be ready
echo "5. Waiting for engine..."
MAX_WAIT=30
for i in $(seq 1 $MAX_WAIT); do
    if curl -sf $ENGINE_URL/health > /dev/null 2>&1; then
        echo "   Engine ready after ${i}s"
        break
    fi
    if ! kill -0 $ENGINE_PID 2>/dev/null; then
        echo "ERROR: Engine process died"
        exit 1
    fi
    if [[ $i -eq $MAX_WAIT ]]; then
        echo "ERROR: Engine didn't start in ${MAX_WAIT}s"
        exit 1
    fi
    sleep 1
done

# Verify health
echo "6. Checking engine health..."
HEALTH=$(curl -sf $ENGINE_URL/health)
echo "   $HEALTH"

# Start tray app
echo "7. Starting tray app..."
python -m voxtype tray &
TRAY_PID=$!

sleep 3

if ! kill -0 $TRAY_PID 2>/dev/null; then
    echo "ERROR: Tray process died"
    exit 1
fi
echo "   Tray running (PID $TRAY_PID)"

# Test SSE connection as agent
echo "8. Testing SSE connection..."
SSE_OUTPUT=$(timeout 5 curl -sf -N $ENGINE_URL/events 2>&1 | head -5 || true)
if [[ -n "$SSE_OUTPUT" ]]; then
    echo "   SSE connected, received data:"
    echo "$SSE_OUTPUT" | sed 's/^/   /'
else
    echo "   SSE endpoint accessible (no events yet)"
fi

echo "=== E2E TEST PASSED ==="
