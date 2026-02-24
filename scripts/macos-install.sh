#!/usr/bin/env bash
# Rebuild dictare wheel and reinstall via Homebrew.
# Works on both macOS and Linux (Linuxbrew).
# Usage: ./scripts/brew-rebuild.sh
set -euo pipefail

BREW_PREFIX="$(brew --prefix)"
# Homebrew tap path differs: macOS uses $PREFIX/Library, Linux uses $PREFIX/Homebrew/Library
FORMULA="$(brew --repository)/Library/Taps/dragfly/homebrew-dictare/Formula/dictare.rb"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="${PROJECT_DIR}/dist"

# openvip tarball: relative to project dir (../../openvip-dev/sdks/python)
OPENVIP_DIR="$(cd "${PROJECT_DIR}/../../openvip-dev/sdks/python" && pwd)"
OPENVIP_TARBALL="${OPENVIP_DIR}/dist/openvip-1.1.0.tar.gz"

# ---------- Helpers ----------

stop_services() {
    echo "==> Stopping services..."
    "${BREW_PREFIX}/bin/dictare" tray stop 2>/dev/null || true
    "${BREW_PREFIX}/bin/dictare" service stop 2>/dev/null || true
}

start_services() {
    echo "==> Starting service..."
    if "${BREW_PREFIX}/bin/dictare" service status 2>/dev/null | grep -q "installed"; then
        "${BREW_PREFIX}/bin/dictare" service start 2>&1
    else
        "${BREW_PREFIX}/bin/dictare" service install 2>&1
    fi
    echo "==> Done. Use 'dictare tray start' for the tray icon."
}

# ---------- 1. Read version from source ----------
VERSION=$(.venv/bin/python -c "
import re, pathlib
text = pathlib.Path('${PROJECT_DIR}/src/dictare/__init__.py').read_text()
print(re.search(r'__version__\s*=\s*\"(.+?)\"', text).group(1))
")
TARBALL="${DIST_DIR}/dictare-${VERSION}.tar.gz"
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
stop_services

# ---------- 6. Reinstall ----------
echo "==> brew reinstall dictare..."
# Note: brew may exit 1 due to dylib linkage warnings (e.g. PyAV) — not fatal
brew reinstall dictare 2>&1 || true

# ---------- 7. Verify ----------
INSTALLED=$("${BREW_PREFIX}/bin/dictare" --version 2>&1)
echo "==> Installed: ${INSTALLED}"
if [[ "$INSTALLED" != *"$VERSION"* ]]; then
    echo "ERROR: installed version does not match expected ${VERSION}" >&2
    exit 1
fi

# ---------- 8. Restart service ----------
start_services
