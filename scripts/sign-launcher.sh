#!/usr/bin/env bash
# Build, sign, and optionally notarize the Swift launcher.
# Usage:
#   ./scripts/sign-launcher.sh                    # build + sign only
#   ./scripts/sign-launcher.sh --notarize         # build + sign + notarize
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SWIFT_SRC="${PROJECT_DIR}/src/dictare/resources/launcher.swift"
ENTITLEMENTS="${PROJECT_DIR}/src/dictare/resources/Dictare.entitlements"
BUILD_DIR="${PROJECT_DIR}/build/launcher"
IDENTITY="${DICTARE_SIGN_IDENTITY:-Developer ID Application}"

mkdir -p "$BUILD_DIR"

# 1. Compile universal binary (arm64 + x86_64)
echo "==> Compiling arm64..."
swiftc -O -target arm64-apple-macos13.0 -o "$BUILD_DIR/Dictare-arm64" "$SWIFT_SRC"
echo "==> Compiling x86_64..."
swiftc -O -target x86_64-apple-macos13.0 -o "$BUILD_DIR/Dictare-x86_64" "$SWIFT_SRC"
echo "==> Creating universal binary..."
lipo -create -output "$BUILD_DIR/Dictare" \
  "$BUILD_DIR/Dictare-arm64" "$BUILD_DIR/Dictare-x86_64"

# 2. Sign with Hardened Runtime
echo "==> Signing with identity: ${IDENTITY}"
codesign --force --options runtime \
  --entitlements "$ENTITLEMENTS" \
  --sign "$IDENTITY" \
  "$BUILD_DIR/Dictare"

codesign --verify --strict "$BUILD_DIR/Dictare"
echo "==> Signed: $BUILD_DIR/Dictare"

# 3. Notarize (optional)
if [[ "${1:-}" == "--notarize" ]]; then
  echo "==> Notarizing..."
  ZIP="$BUILD_DIR/Dictare-launcher.zip"
  ditto -c -k "$BUILD_DIR/Dictare" "$ZIP"
  xcrun notarytool submit "$ZIP" \
    --keychain-profile "dictare-notarize" \
    --wait
  echo "==> Notarized successfully"
fi
