#!/usr/bin/env bash
# Test voxtype installation on multiple distros using Docker.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

ALL_DISTROS=(ubuntu debian fedora arch)
DISTROS=()
TEST_LEVEL="smoke"
OPENVIP_SDK="/home/user/repos/openvip-dev/sdks/python"

# Help
usage() {
    echo "Usage: $0 [OPTIONS] [DISTROS...]"
    echo ""
    echo "Test voxtype installation on Linux distros via Docker."
    echo ""
    echo "Options:"
    echo "  --smoke     Import checks only (default, ~1s)"
    echo "  --engine    Engine start + /health check (~10s)"
    echo "  --tray      Tray app with Xvfb (~10s)"
    echo "  --e2e       Full end-to-end test (~20s)"
    echo "  --all       Test all distros"
    echo "  -h, --help  Show this help"
    echo ""
    echo "Distros: ubuntu, debian, fedora, arch"
    echo ""
    echo "Examples:"
    echo "  $0                    # smoke test on all distros"
    echo "  $0 ubuntu             # smoke test on ubuntu"
    echo "  $0 --engine ubuntu    # engine test on ubuntu"
    echo "  $0 --e2e --all        # full e2e on all distros"
    exit 0
}

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --smoke)  TEST_LEVEL="smoke"; shift ;;
        --engine) TEST_LEVEL="engine"; shift ;;
        --tray)   TEST_LEVEL="tray"; shift ;;
        --e2e)    TEST_LEVEL="e2e"; shift ;;
        --all)    DISTROS=("${ALL_DISTROS[@]}"); shift ;;
        -h|--help) usage ;;
        -*) echo "Unknown option: $1"; usage ;;
        *)  DISTROS+=("$1"); shift ;;
    esac
done

# Default to all distros if none specified
if [[ ${#DISTROS[@]} -eq 0 ]]; then
    DISTROS=("${ALL_DISTROS[@]}")
fi

echo -e "${BOLD}Testing voxtype on: ${DISTROS[*]}${RESET}"
echo -e "${CYAN}Test level: ${TEST_LEVEL}${RESET}"
echo ""

# Copy openvip SDK to project dir for Docker context
if [[ -d "$OPENVIP_SDK" ]]; then
    echo -e "${YELLOW}▶ Copying openvip SDK to Docker context...${RESET}"
    rm -rf "$PROJECT_DIR/_openvip_sdk"
    cp -r "$OPENVIP_SDK" "$PROJECT_DIR/_openvip_sdk"
    trap "rm -rf '$PROJECT_DIR/_openvip_sdk'" EXIT
else
    echo -e "${RED}✗ openvip SDK not found at: $OPENVIP_SDK${RESET}"
    exit 1
fi

# For engine/e2e tests: ensure models are downloaded on host
if [[ "$TEST_LEVEL" == "engine" || "$TEST_LEVEL" == "e2e" ]]; then
    HF_CACHE="${HOME}/.cache/huggingface/hub"
    WHISPER_MODEL="$HF_CACHE/models--mobiuslabsgmbh--faster-whisper-large-v3-turbo"
    if [[ ! -d "$WHISPER_MODEL" ]]; then
        echo -e "${YELLOW}▶ Downloading required models (first time only)...${RESET}"
        cd "$PROJECT_DIR"
        uv run python -m voxtype models download
        cd - > /dev/null
    else
        echo -e "${GREEN}✓ Models already cached${RESET}"
    fi
fi

RESULTS=()

for distro in "${DISTROS[@]}"; do
    dockerfile="$SCRIPT_DIR/Dockerfile.$distro"

    if [[ ! -f "$dockerfile" ]]; then
        echo -e "${RED}✗ $distro${RESET} — Dockerfile not found: $dockerfile"
        RESULTS+=("$distro:SKIP")
        continue
    fi

    echo -e "${YELLOW}▶ Testing $distro (${TEST_LEVEL})...${RESET}"

    image_name="voxtype-test-$distro"
    log_file="/tmp/voxtype-test-$distro-$TEST_LEVEL.log"

    # Build the image
    if ! docker build -t "$image_name" -f "$dockerfile" "$PROJECT_DIR" 2>&1 | tee "$log_file"; then
        echo -e "${RED}✗ $distro${RESET} — build failed (see $log_file)"
        RESULTS+=("$distro:FAIL")
        continue
    fi

    # Run the test
    if [[ "$TEST_LEVEL" != "smoke" ]]; then
        echo -e "${CYAN}  Running ${TEST_LEVEL} test...${RESET}"
        # Mount HuggingFace cache for models (avoids re-downloading)
        HF_CACHE="${HOME}/.cache/huggingface"
        MOUNT_OPTS=""
        if [[ -d "$HF_CACHE" ]]; then
            MOUNT_OPTS="-v ${HF_CACHE}:/root/.cache/huggingface:ro"
        fi
        if docker run --rm $MOUNT_OPTS "$image_name" /app/scripts/test-distros/tests/${TEST_LEVEL}.sh 2>&1 | tee -a "$log_file"; then
            echo -e "${GREEN}✓ $distro${RESET} — ${TEST_LEVEL} passed"
            RESULTS+=("$distro:PASS")
        else
            echo -e "${RED}✗ $distro${RESET} — ${TEST_LEVEL} failed (see $log_file)"
            RESULTS+=("$distro:FAIL")
        fi
    else
        # Smoke test is part of the build
        echo -e "${GREEN}✓ $distro${RESET} — ${TEST_LEVEL} passed"
        RESULTS+=("$distro:PASS")
    fi
    echo ""
done

# Summary
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}Results (${TEST_LEVEL}):${RESET}"
FAILED=0
for result in "${RESULTS[@]}"; do
    distro="${result%%:*}"
    status="${result##*:}"
    case "$status" in
        PASS) echo -e "  ${GREEN}✓${RESET} $distro" ;;
        FAIL) echo -e "  ${RED}✗${RESET} $distro"; FAILED=1 ;;
        SKIP) echo -e "  ${YELLOW}○${RESET} $distro (skipped)" ;;
    esac
done

exit $FAILED
