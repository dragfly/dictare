#!/usr/bin/env bash
# Rebuild dictare wheel and reinstall via Homebrew.
# Works on both macOS and Linux (Linuxbrew).
# Usage: ./scripts/brew-rebuild.sh
set -euo pipefail

BREW_PREFIX="$(brew --prefix)"
# Homebrew tap path differs: macOS uses $PREFIX/Library, Linux uses $PREFIX/Homebrew/Library
FORMULA="$(brew --repository)/Library/Taps/dragfly/homebrew-tap/Formula/dictare.rb"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="${PROJECT_DIR}/dist"

# openvip tarball: auto-detect version from SDK's pyproject.toml
OPENVIP_DIR="$(cd "${PROJECT_DIR}/../../openvip-dev/sdks/python" && pwd)"
OPENVIP_VERSION=$(grep '^version' "${OPENVIP_DIR}/pyproject.toml" | head -1 | sed 's/.*= *"\(.*\)"/\1/')
OPENVIP_TARBALL="${OPENVIP_DIR}/dist/openvip-${OPENVIP_VERSION}.tar.gz"

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

# ---------- 1. Ensure uv is available ----------
if ! command -v uv &>/dev/null; then
    echo "==> Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    command -v uv &>/dev/null || { echo "ERROR: uv installation failed" >&2; exit 1; }
fi

# ---------- 2. Read version from source (no venv needed) ----------
VERSION=$(grep -E '^__version__' "${PROJECT_DIR}/src/dictare/__init__.py" | sed 's/.*"\(.*\)"/\1/')
TARBALL="${DIST_DIR}/dictare-${VERSION}.tar.gz"
echo "==> Version: ${VERSION}"
echo "==> Brew prefix: ${BREW_PREFIX}"

# ---------- 3. Build openvip tarball if missing ----------
if [[ ! -f "$OPENVIP_TARBALL" ]]; then
    echo "==> Building openvip tarball..."
    cd "$OPENVIP_DIR"
    uv build --sdist --quiet
    cd "$PROJECT_DIR"
fi
if [[ ! -f "$OPENVIP_TARBALL" ]]; then
    echo "ERROR: openvip tarball not found: $OPENVIP_TARBALL" >&2
    exit 1
fi
echo "==> openvip: ${OPENVIP_TARBALL}"

# ---------- 4. Build sdist ----------
echo "==> Building sdist..."
cd "$PROJECT_DIR"
uv build --sdist --quiet
if [[ ! -f "$TARBALL" ]]; then
    echo "ERROR: expected tarball not found: $TARBALL" >&2
    exit 1
fi

# ---------- 4. Compute sha256 ----------
if command -v shasum &>/dev/null; then
    SHA=$(shasum -a 256 "$TARBALL" | awk '{print $1}')
else
    SHA=$(sha256sum "$TARBALL" | awk '{print $1}')
fi
echo "==> SHA256: ${SHA}"

# ---------- 5. Update Homebrew formula ----------
echo "==> Updating formula..."
# sed -i differs between macOS (BSD) and Linux (GNU)
if [[ "$(uname -s)" == "Darwin" ]]; then
    SED_INPLACE=(sed -i '')
else
    SED_INPLACE=(sed -i)
fi
"${SED_INPLACE[@]}" \
    -e "s|url \".*\"|url \"file://${TARBALL}\"|" \
    -e "s|sha256 \".*\"|sha256 \"${SHA}\"|" \
    -e "s|openvip_tarball = \".*\"|openvip_tarball = \"${OPENVIP_TARBALL}\"|" \
    -e "s|assert_match \"[^\"]*\", shell_output|assert_match \"${VERSION}\", shell_output|" \
    "$FORMULA"

# ---------- 6. Stop running services ----------
stop_services

# ---------- 7. Reinstall ----------
echo "==> brew reinstall dictare..."
# Note: brew may exit 1 due to dylib linkage warnings (e.g. PyAV) — not fatal
brew reinstall dictare 2>&1 || true

# ---------- 7b. Restore formula to clean public state ----------
# The formula was temporarily modified with local file:// paths for the dev
# build. Restore it immediately after reinstall so the tap repo never has
# local paths committed (prevents accidental leaks if someone pushes the tap).
TAP_DIR="$(brew --repository)/Library/Taps/dragfly/homebrew-tap"
git -C "$TAP_DIR" checkout -- Formula/dictare.rb
echo "==> Formula restored to clean state"

# ---------- 8. Verify ----------
INSTALLED=$("${BREW_PREFIX}/bin/dictare" --version 2>&1)
echo "==> Installed: ${INSTALLED}"
if [[ "$INSTALLED" != *"$VERSION"* ]]; then
    echo "ERROR: installed version does not match expected ${VERSION}" >&2
    exit 1
fi

# ---------- 9. Restart service ----------
start_services
