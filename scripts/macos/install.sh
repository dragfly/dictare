#!/usr/bin/env bash
# Rebuild dictare wheel and reinstall via Homebrew.
# openvip is now on PyPI — no local tarball needed.
# Usage: ./scripts/macos-install.sh
set -euo pipefail

BREW_PREFIX="$(brew --prefix)"
FORMULA="$(brew --repository)/Library/Taps/dragfly/homebrew-tap/Formula/dictare.rb"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
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
    # The signed+notarized .app bundle is downloaded from GitHub Release and
    # placed in ~/Applications/Dictare.app.  python_path is written externally
    # to ~/.dictare/python_path so the signed bundle stays immutable.
    #
    # Lookup order for pre-built bundle:
    #   1. Cellar (Homebrew formula resource — future)
    #   2. Local build (./build/bundle/)
    #   3. GitHub Release (download complete .app bundle)
    APP_DEST="$HOME/Applications/Dictare.app"
    BUNDLE_FOUND=""

    # Check local pre-built bundle
    for candidate in \
        "${BREW_PREFIX}/opt/dictare/libexec/bundle/Dictare.app" \
        "${PROJECT_DIR}/build/bundle/Dictare.app"
    do
        if [[ -d "$candidate" ]]; then
            echo "==> Using local pre-built bundle: $candidate"
            mkdir -p "$HOME/Applications"
            if [[ -d "$APP_DEST" ]]; then
                rm -rf "$APP_DEST"
            fi
            cp -R "$candidate" "$APP_DEST"
            xattr -dr com.apple.quarantine "$APP_DEST" 2>/dev/null || true
            BUNDLE_FOUND="true"
            break
        fi
    done

    # Download complete .app bundle from GitHub Release
    if [[ -z "$BUNDLE_FOUND" ]] && command -v gh &>/dev/null; then
        echo "==> Checking GitHub Release for signed bundle..."
        RELEASE_DIR="${PROJECT_DIR}/build/bundle"
        mkdir -p "$RELEASE_DIR"
        RELEASE_ZIP="${RELEASE_DIR}/Dictare-launcher.zip"
        if gh release download "launcher" \
            --repo dragfly/dictare \
            --pattern "Dictare-launcher-universal.zip" \
            --output "$RELEASE_ZIP" 2>/dev/null; then
            # Extract .app bundle from zip.
            # --keepParent zips yield Dictare.app/Contents/..., old zips
            # yield Contents/... directly — handle both.
            EXTRACT_DIR="${RELEASE_DIR}/extract"
            mkdir -p "$EXTRACT_DIR"
            ditto -x -k "$RELEASE_ZIP" "$EXTRACT_DIR"
            rm -f "$RELEASE_ZIP"
            if [[ -d "${EXTRACT_DIR}/Dictare.app" ]]; then
                mv "${EXTRACT_DIR}/Dictare.app" "${RELEASE_DIR}/Dictare.app"
            elif [[ -d "${EXTRACT_DIR}/Contents" ]]; then
                mkdir -p "${RELEASE_DIR}/Dictare.app"
                mv "${EXTRACT_DIR}/Contents" "${RELEASE_DIR}/Dictare.app/Contents"
            fi
            rmdir "$EXTRACT_DIR" 2>/dev/null || true
            if [[ -d "${RELEASE_DIR}/Dictare.app" ]]; then
                mkdir -p "$HOME/Applications"
                if [[ -d "$APP_DEST" ]]; then
                    rm -rf "$APP_DEST"
                fi
                cp -R "${RELEASE_DIR}/Dictare.app" "$APP_DEST"
                xattr -dr com.apple.quarantine "$APP_DEST" 2>/dev/null || true
                BUNDLE_FOUND="true"
                echo "==> Downloaded signed bundle from GitHub Release"
            fi
        else
            echo "==> No signed bundle in GitHub Release"
        fi
    fi

    # Fallback: check for pre-built binary only (legacy flow)
    if [[ -z "$BUNDLE_FOUND" ]]; then
        PREBUILT=""
        for candidate in \
            "${BREW_PREFIX}/opt/dictare/libexec/launcher/Dictare" \
            "${PROJECT_DIR}/build/launcher/Dictare"
        do
            if [[ -f "$candidate" ]]; then
                PREBUILT="$candidate"
                xattr -d com.apple.quarantine "$PREBUILT" 2>/dev/null || true
                break
            fi
        done
        if [[ -n "$PREBUILT" ]]; then
            echo "==> Using pre-built launcher binary (legacy): $PREBUILT"
            "${BREW_PREFIX}/bin/dictare" service install --prebuilt-launcher "$PREBUILT" 2>&1
            echo "==> Done."
            return
        fi
    fi

    # service install writes ~/.dictare/python_path and creates launchd plist.
    # When a signed bundle is already in ~/Applications, it skips bundle creation.
    "${BREW_PREFIX}/bin/dictare" service install 2>&1
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
# Always rebuild from working tree — remove stale tarball so uv doesn't skip
rm -f "$TARBALL"
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
# Replace formula url/sha256 with local tarball.
# Use 2-space indent anchor to avoid replacing the launcher resource (4-space).
"${SED_INPLACE[@]}" \
    -e "s|^  url \".*\"|  url \"file://${TARBALL}\"|" \
    -e "s|^  sha256 \".*\"|  sha256 \"${SHA}\"|" \
    -e "s|dictare_tarball = \".*\"|dictare_tarball = \"${TARBALL}\"|" \
    -e "s|assert_match \"[^\"]*\", shell_output|assert_match \"${VERSION}\", shell_output|" \
    -e "s|dictare#{extras}==[^\"]*\"|dictare#{extras}==${VERSION}\"|" \
    "$FORMULA"

# ---------- 5a. Strip launcher resource (private repo, can't download) ----------
# The launcher is installed later by start_services via gh (which has auth).
# Remove the resource block and its stage block from the local formula copy.
"${SED_INPLACE[@]}" \
    -e '/resource "launcher" do/,/^  end/d' \
    -e '/resource("launcher").stage do/,/^    end/d' \
    "$FORMULA"

# ---------- 5b. Inject --find-links and --reinstall for local dist ----------
"${SED_INPLACE[@]}" \
    "/\"--prerelease=allow\"/a\\
           \"--reinstall\",\\
           \"--find-links\", \"${DIST_DIR}\"," \
    "$FORMULA"

# ---------- 5c. Inject local SDK if available (set by full-install.sh) ----------
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
# Clear Homebrew download cache for dictare so it fetches the new tarball.
brew --cache dictare 2>/dev/null | xargs rm -f 2>/dev/null || true
find "$(brew --cache)/downloads/" -name "*dictare*" -delete 2>/dev/null || true
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
