#!/usr/bin/env bash
# Rebuild voxtype wheel and reinstall via Homebrew.
# Usage: ./scripts/brew-rebuild.sh
set -euo pipefail

FORMULA="/opt/homebrew/Library/Taps/dragfly/homebrew-voxtype/Formula/voxtype.rb"
OPENVIP_TARBALL="/home/user/repos/nottoplay/openvip-sdks/python/dist/openvip-1.1.0.tar.gz"
DIST_DIR="$(cd "$(dirname "$0")/.." && pwd)/dist"

# ---------- 1. Read version from source ----------
VERSION=$(python3.11 -c "
import re, pathlib
text = pathlib.Path('src/voxtype/__init__.py').read_text()
print(re.search(r'__version__\\s*=\\s*\"(.+?)\"', text).group(1))
")
TARBALL="${DIST_DIR}/voxtype-${VERSION}.tar.gz"
echo "==> Version: ${VERSION}"

# ---------- 2. Build sdist ----------
echo "==> Building sdist..."
uv build --sdist --quiet
if [[ ! -f "$TARBALL" ]]; then
    echo "ERROR: expected tarball not found: $TARBALL" >&2
    exit 1
fi

# ---------- 3. Compute sha256 ----------
SHA=$(shasum -a 256 "$TARBALL" | awk '{print $1}')
echo "==> SHA256: ${SHA}"

# ---------- 4. Update Homebrew formula ----------
echo "==> Updating formula..."
sed -i '' \
    -e "s|url \"file:///.*\"|url \"file://${TARBALL}\"|" \
    -e "s|sha256 \".*\"|sha256 \"${SHA}\"|" \
    -e "s|assert_match \"[^\"]*\", shell_output|assert_match \"${VERSION}\", shell_output|" \
    "$FORMULA"

# ---------- 5. Stop running services ----------
echo "==> Stopping services..."
/opt/homebrew/bin/voxtype tray stop 2>/dev/null || true
/opt/homebrew/bin/voxtype service uninstall 2>/dev/null || true

# ---------- 6. Reinstall ----------
echo "==> brew reinstall voxtype..."
brew reinstall voxtype 2>&1 | tail -3

# ---------- 7. Verify ----------
INSTALLED=$(/opt/homebrew/bin/voxtype --version 2>&1)
echo "==> Installed: ${INSTALLED}"

# ---------- 8. Restart services ----------
echo "==> Restarting service + tray..."
/opt/homebrew/bin/voxtype service install 2>&1
sleep 2
/opt/homebrew/bin/voxtype tray start 2>&1

echo "==> Done."
