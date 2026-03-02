#!/usr/bin/env bash
# Full dev install: regenerate SDK from local protocol spec, then install dictare.
#
# Use this when you've changed:
#   - the OpenVIP protocol spec  (../openvip-dev/protocol/bindings/http/openapi.yaml)
#   - the SDK handwritten layer  (../openvip-dev/sdks/python/openvip/client.py etc.)
#
# Use ./scripts/install.sh instead when you've only changed dictare itself.
#
# Assumes the standard repo layout:
#   ~/repos/oss/openvip-dev/
#     protocol/   ← OpenVIP spec
#     sdks/       ← SDK (generate.sh lives here)
#   ~/repos/oss/dictare/    ← this repo
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SDKS_DIR="${PROJECT_DIR}/../openvip-dev/sdks"
PROTOCOL_SPEC="${PROJECT_DIR}/../openvip-dev/protocol/bindings/http/openapi.yaml"
PYPROJECT="${PROJECT_DIR}/pyproject.toml"

# ---------- 1. Validate paths ----------
[[ -f "$PROTOCOL_SPEC" ]] || { echo "ERROR: spec not found: $PROTOCOL_SPEC" >&2; exit 1; }
[[ -f "${SDKS_DIR}/generate.sh" ]] || { echo "ERROR: generate.sh not found in $SDKS_DIR" >&2; exit 1; }

# ---------- 2. Regenerate SDK from local spec ----------
echo "==> Regenerating SDK from local protocol spec..."
cd "$SDKS_DIR"
./generate.sh "$PROTOCOL_SPEC" --only python

# ---------- 3. Ensure [tool.uv.sources] override points to local SDK ----------
SDK_PATH_REAL="$(cd "${SDKS_DIR}/python" && pwd)"
# Use relative path from project dir to avoid leaking usernames
SDK_PATH_REL="$(python3 -c "import os; print(os.path.relpath('${SDK_PATH_REAL}', '${PROJECT_DIR}'))")"

if grep -q '^\[tool\.uv\.sources\]' "$PYPROJECT"; then
    if grep -q 'openvip' "$PYPROJECT"; then
        echo "==> [tool.uv.sources] already set — skipping"
    else
        # sources block exists but no openvip entry — add it
        sed -i '' "/^\[tool\.uv\.sources\]/a\\
openvip = { path = \"${SDK_PATH_REL}\" }
" "$PYPROJECT"
        echo "==> Added openvip override to existing [tool.uv.sources]"
    fi
else
    # No sources block — append it
    printf '\n[tool.uv.sources]\nopenvip = { path = "%s" }\n' "$SDK_PATH_REL" >> "$PYPROJECT"
    echo "==> Added [tool.uv.sources] with openvip override"
fi

# ---------- 4. Build SDK sdist ----------
echo "==> Building SDK sdist..."
cd "$SDK_PATH_REAL"
uv build --sdist --quiet
export OPENVIP_SDK_DIST="${SDK_PATH_REAL}/dist"
echo "==> SDK dist: ${OPENVIP_SDK_DIST}"

# ---------- 5. Build UI ----------
echo "==> Building UI..."
cd "${PROJECT_DIR}/ui"
pnpm install --frozen-lockfile --silent
pnpm run build

# ---------- 6. Update lock file ----------
echo "==> Updating uv.lock..."
cd "$PROJECT_DIR"
uv lock --python 3.11

# ---------- 7. Install ----------
echo "==> Installing dictare..."
exec "${SCRIPT_DIR}/install.sh"
