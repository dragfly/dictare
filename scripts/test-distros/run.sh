#!/usr/bin/env bash
# Test linux-install.sh on multiple distros using Docker.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
RESET='\033[0m'

DISTROS=(ubuntu debian fedora arch)
OPENVIP_SDK="/home/user/repos/openvip-dev/sdks/python"

# Parse args
if [[ $# -gt 0 ]]; then
    DISTROS=("$@")
fi

echo -e "${BOLD}Testing linux-install.sh on: ${DISTROS[*]}${RESET}"
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

RESULTS=()

for distro in "${DISTROS[@]}"; do
    dockerfile="$SCRIPT_DIR/Dockerfile.$distro"

    if [[ ! -f "$dockerfile" ]]; then
        echo -e "${RED}✗ $distro${RESET} — Dockerfile not found: $dockerfile"
        RESULTS+=("$distro:SKIP")
        continue
    fi

    echo -e "${YELLOW}▶ Testing $distro...${RESET}"

    image_name="voxtype-test-$distro"

    if docker build -t "$image_name" -f "$dockerfile" "$PROJECT_DIR" 2>&1 | tee "/tmp/voxtype-test-$distro.log"; then
        echo -e "${GREEN}✓ $distro${RESET} — install succeeded"
        RESULTS+=("$distro:PASS")
    else
        echo -e "${RED}✗ $distro${RESET} — install failed (see /tmp/voxtype-test-$distro.log)"
        RESULTS+=("$distro:FAIL")
    fi
    echo ""
done

# Summary
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}Results:${RESET}"
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
