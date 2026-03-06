#!/usr/bin/env bash
# Rebuild dictare wheel and reinstall via Homebrew.
# openvip is now on PyPI — no local tarball needed.
# Usage: ./scripts/macos-install.sh
set -euo pipefail

BREW_PREFIX="$(brew --prefix)"
FORMULA="$(brew --repository)/Library/Taps/dragfly/homebrew-tap/Formula/dictare.rb"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="${PROJECT_DIR}/dist"

# ---------- Constants ----------

LABEL="dev.dragfly.dictare"
TRAY_LABEL="dev.dragfly.dictare.tray"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
TRAY_PLIST="$HOME/Library/LaunchAgents/${TRAY_LABEL}.plist"

# ---------- Helpers ----------

stop_services() {
    # Unload LaunchAgents directly — do NOT depend on the dictare binary,
    # which lives in the Cellar that brew reinstall is about to delete.
    # launchctl unload also disables KeepAlive, preventing the race condition
    # where launchd restarts the engine mid-reinstall.
    echo "==> Unloading LaunchAgents..."
    launchctl unload "$TRAY_PLIST" 2>/dev/null || true
    launchctl unload "$PLIST" 2>/dev/null || true

    # Kill any orphan processes that survived unload (e.g., old launcher
    # without proper SIGTERM handling, or processes from a previous crash).
    pkill -f "Dictare.app/Contents/MacOS/Dictare" 2>/dev/null || true
    pkill -f "dictare serve" 2>/dev/null || true
    pkill -f "dictare.tray" 2>/dev/null || true

    # Brief pause to let processes actually exit before brew wipes the Cellar.
    sleep 1
}

start_services() {
    echo "==> Starting service..."
    # Always run service install after a version bump — it updates python_path
    # inside Dictare.app (the Swift launcher reads it to find the new Cellar Python).
    # service start alone leaves the old path pointing to the deleted Cellar dir.
    # If a pre-built signed launcher exists in the Cellar, use it (stable TCC via
    # Developer ID, no swiftc needed, no Gatekeeper warnings).
    # Look for pre-built signed launcher:
    #   1. Cellar (Homebrew formula resource)
    #   2. Local build (./scripts/macos/sign-launcher.sh)
    #   3. GitHub Release (download for this version)
    PREBUILT=""
    for candidate in \
        "${BREW_PREFIX}/opt/dictare/libexec/launcher/Dictare" \
        "${PROJECT_DIR}/build/launcher/Dictare"
    do
        if [[ -f "$candidate" ]]; then
            PREBUILT="$candidate"
            break
        fi
    done

    # If no local launcher, try downloading from GitHub Release
    if [[ -z "$PREBUILT" ]] && command -v gh &>/dev/null; then
        echo "==> Checking GitHub Release for signed launcher..."
        RELEASE_DIR="${PROJECT_DIR}/build/launcher"
        mkdir -p "$RELEASE_DIR"
        RELEASE_ZIP="${RELEASE_DIR}/Dictare-launcher.zip"
        if gh release download "v${VERSION}" \
            --repo dragfly/dictare \
            --pattern "Dictare-launcher-*-universal.zip" \
            --output "$RELEASE_ZIP" 2>/dev/null; then
            ditto -x -k "$RELEASE_ZIP" "$RELEASE_DIR"
            rm -f "$RELEASE_ZIP"
            if [[ -f "${RELEASE_DIR}/Dictare" ]]; then
                PREBUILT="${RELEASE_DIR}/Dictare"
                echo "==> Downloaded signed launcher from GitHub Release"
            fi
        else
            echo "==> No signed launcher in GitHub Release (compiling locally)"
        fi
    fi

    if [[ -n "$PREBUILT" ]]; then
        echo "==> Using pre-built signed launcher: $PREBUILT"
        "${BREW_PREFIX}/bin/dictare" service install --prebuilt-launcher "$PREBUILT" 2>&1
    else
        "${BREW_PREFIX}/bin/dictare" service install 2>&1
    fi
    echo "==> Done."
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

# ---------- 3. Build sdist ----------
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
if [[ "$(uname -s)" == "Darwin" ]]; then
    SED_INPLACE=(sed -i '')
else
    SED_INPLACE=(sed -i)
fi
"${SED_INPLACE[@]}" \
    -e "s|url \".*\"|url \"file://${TARBALL}\"|" \
    -e "s|sha256 \".*\"|sha256 \"${SHA}\"|" \
    -e "s|dictare_tarball = \".*\"|dictare_tarball = \"${TARBALL}\"|" \
    -e "s|assert_match \"[^\"]*\", shell_output|assert_match \"${VERSION}\", shell_output|" \
    "$FORMULA"

# ---------- 5b. Inject local SDK if available (set by full-install.sh) ----------
if [[ -n "${OPENVIP_SDK_DIST:-}" ]]; then
    echo "==> Injecting local SDK from ${OPENVIP_SDK_DIST}"
    "${SED_INPLACE[@]}" \
        "/\"--prerelease=allow\"/a\\
           \"--find-links\", \"${OPENVIP_SDK_DIST}\"," \
        "$FORMULA"
fi

# ---------- 6. Stop running services ----------
stop_services

# ---------- 7. Reinstall ----------
echo "==> brew reinstall dictare..."
# Note: brew may exit 1 due to dylib linkage warnings (e.g. PyAV) — not fatal
brew reinstall dictare 2>&1 || true

# ---------- 7b. Restore formula to clean public state ----------
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
