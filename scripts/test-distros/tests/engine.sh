#!/usr/bin/env bash
# Engine test: start engine and verify /health endpoint
# NOTE: Requires audio devices and models. Skipped in Docker (no audio).
set -euo pipefail

echo "=== ENGINE TEST ==="

if [[ "${VOXTYPE_SKIP_ENGINE_TEST:-}" == "1" ]]; then
    echo "SKIPPED: VOXTYPE_SKIP_ENGINE_TEST=1"
    exit 0
fi

# Check for audio devices (not available in Docker)
echo "1. Checking for audio devices..."
AUDIO_DEVS=$(python -c "import sounddevice as sd; devs = [d for d in sd.query_devices() if d['max_input_channels'] > 0]; print(len(devs))" 2>/dev/null || echo "0")
echo "   Found $AUDIO_DEVS input devices"
if [[ "$AUDIO_DEVS" == "0" ]]; then
    echo "   No audio input devices found (likely running in Docker)"
    echo "   Engine test requires audio hardware"
    echo "SKIPPED: No audio devices"
    exit 0
fi

ENGINE_URL="http://127.0.0.1:8770"

# Check if models are available (HuggingFace cache)
echo "2. Checking for models..."
HF_CACHE="${HF_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/huggingface}/hub"
WHISPER_MODEL="$HF_CACHE/models--mobiuslabsgmbh--faster-whisper-large-v3-turbo"
if [[ ! -d "$WHISPER_MODEL" ]]; then
    echo "   No whisper model found in $WHISPER_MODEL"
    echo "   Run 'voxtype models download' first, or mount HF cache"
    echo "SKIPPED: Models not available"
    exit 0
fi
echo "   Whisper model found"

# Start engine in background (verbose mode to disable interactive panel)
echo "3. Starting engine..."
python -m voxtype engine start --verbose 2>&1 &
ENGINE_PID=$!

# Cleanup on exit
cleanup() {
    echo "Stopping engine (PID $ENGINE_PID)..."
    kill $ENGINE_PID 2>/dev/null || true
    wait $ENGINE_PID 2>/dev/null || true
}
trap cleanup EXIT

# Wait for engine to be ready
echo "4. Waiting for engine to start..."
MAX_WAIT=60
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

# Check health endpoint
echo "5. Checking /health endpoint..."
HEALTH=$(curl -sf $ENGINE_URL/health)
echo "   Response: $HEALTH"

if echo "$HEALTH" | grep -qi "ok\|healthy\|status"; then
    echo "   Health check OK"
else
    echo "ERROR: Unexpected health response"
    exit 1
fi

# Check that SSE endpoint exists
echo "6. Checking /events endpoint exists..."
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 2 $ENGINE_URL/events || echo "000")
# SSE endpoint should return 200 (and stream), we just check it doesn't 404
if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "000" ]]; then
    echo "   /events endpoint OK (code: $HTTP_CODE)"
else
    echo "ERROR: /events returned $HTTP_CODE"
    exit 1
fi

echo "=== ENGINE TEST PASSED ==="
