#!/usr/bin/env bash
# Rebuild voxtype wheel and reinstall via Homebrew.
# Works on both macOS and Linux (Linuxbrew).
# Usage: ./scripts/brew-rebuild.sh
set -euo pipefail

BREW_PREFIX="$(brew --prefix)"
FORMULA="${BREW_PREFIX}/Library/Taps/dragfly/homebrew-voxtype/Formula/voxtype.rb"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="${PROJECT_DIR}/dist"

# openvip tarball: relative to project dir (../../openvip-dev/sdks/python)
OPENVIP_DIR="$(cd "${PROJECT_DIR}/../../openvip-dev/sdks/python" && pwd)"
OPENVIP_TARBALL="${OPENVIP_DIR}/dist/openvip-1.1.0.tar.gz"

# ---------- 1. Read version from source ----------
VERSION=$(python3.11 -c "
import re, pathlib
text = pathlib.Path('${PROJECT_DIR}/src/voxtype/__init__.py').read_text()
print(re.search(r'__version__\s*=\s*\"(.+?)\"', text).group(1))
")
TARBALL="${DIST_DIR}/voxtype-${VERSION}.tar.gz"
echo "==> Version: ${VERSION}"
echo "==> Brew prefix: ${BREW_PREFIX}"

# ---------- 2. Build sdist ----------
echo "==> Building sdist..."
cd "$PROJECT_DIR"
uv build --sdist --quiet
if [[ ! -f "$TARBALL" ]]; then
    echo "ERROR: expected tarball not found: $TARBALL" >&2
    exit 1
fi

# ---------- 3. Compute sha256 ----------
if command -v shasum &>/dev/null; then
    SHA=$(shasum -a 256 "$TARBALL" | awk '{print $1}')
else
    SHA=$(sha256sum "$TARBALL" | awk '{print $1}')
fi
echo "==> SHA256: ${SHA}"

# ---------- 4. Update Homebrew formula ----------
echo "==> Updating formula..."
# sed -i differs between macOS (BSD) and Linux (GNU)
if [[ "$(uname -s)" == "Darwin" ]]; then
    SED_INPLACE=(sed -i '')
else
    SED_INPLACE=(sed -i)
fi
"${SED_INPLACE[@]}" \
    -e "s|url \"file:///.*\"|url \"file://${TARBALL}\"|" \
    -e "s|sha256 \".*\"|sha256 \"${SHA}\"|" \
    -e "s|assert_match \"[^\"]*\", shell_output|assert_match \"${VERSION}\", shell_output|" \
    "$FORMULA"

# Also update openvip tarball path in formula (may differ per machine)
"${SED_INPLACE[@]}" \
    -e "s|\"/.*/openvip-.*\.tar\.gz\"|\"${OPENVIP_TARBALL}\"|" \
    "$FORMULA"

# ---------- 5. Stop running services ----------
echo "==> Stopping services..."
brew services stop voxtype 2>/dev/null || true
"${BREW_PREFIX}/bin/voxtype" tray stop 2>/dev/null || true

# ---------- 6. Reinstall ----------
echo "==> brew reinstall voxtype..."
# Note: brew may exit 1 due to dylib linkage warnings (e.g. PyAV) — not fatal
brew reinstall voxtype 2>&1 || true

# ---------- 7. Verify ----------
INSTALLED=$("${BREW_PREFIX}/bin/voxtype" --version 2>&1)
echo "==> Installed: ${INSTALLED}"
if [[ "$INSTALLED" != *"$VERSION"* ]]; then
    echo "ERROR: installed version does not match expected ${VERSION}" >&2
    exit 1
fi

# ---------- 8. Restart service ----------
echo "==> Starting service..."
brew services start voxtype 2>&1

echo "==> Done. Use 'voxtype tray start' for the tray icon."
