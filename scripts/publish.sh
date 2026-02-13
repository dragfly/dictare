#!/usr/bin/env bash
# Publish openvip + voxtype to PyPI
#
# Usage:
#   ./scripts/publish.sh              # interactive, asks before each step
#   ./scripts/publish.sh --dry-run    # build only, no upload
#
# Prerequisites:
#   - PyPI API tokens configured (OPENVIP_PYPI_TOKEN + VOXTYPE_PYPI_TOKEN env vars,
#     or ~/.pypirc, or uv keyring)
#   - All tests passing
#   - Version bumped in both projects
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VOXTYPE_DIR="$(dirname "$SCRIPT_DIR")"
OPENVIP_DIR="/home/user/repos/nottoplay/openvip-sdks/python"

# ─── Helpers ───────────────────────────────────────────────────────────
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
RESET='\033[0m'

info()    { printf "${GREEN}==>${RESET} ${BOLD}%s${RESET}\n" "$*"; }
ok()      { printf "${GREEN}==>${RESET} %s\n" "$*"; }
warn()    { printf "${YELLOW}==>${RESET} %s\n" "$*"; }
error()   { printf "${RED}ERROR:${RESET} %s\n" "$*" >&2; exit 1; }

confirm() {
    if [[ "$DRY_RUN" == true ]]; then
        warn "[dry-run] Would ask: $1"
        return 0
    fi
    printf "${BOLD}%s${RESET} [y/N] " "$1"
    read -r answer
    [[ "$answer" =~ ^[Yy]$ ]] || { warn "Skipped."; return 1; }
}

# ─── Parse flags ───────────────────────────────────────────────────────
DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --help|-h)
            cat <<'EOF'
Publish openvip + voxtype to PyPI

Usage:
  ./scripts/publish.sh              Interactive publish
  ./scripts/publish.sh --dry-run    Build only, no upload

Steps:
  1. Run tests
  2. Verify versions are aligned
  3. Build + publish openvip to PyPI
  4. Build + publish voxtype to PyPI
  5. Create git tag + GitHub release

Environment variables (for non-interactive upload):
  OPENVIP_PYPI_TOKEN   PyPI API token for openvip
  VOXTYPE_PYPI_TOKEN   PyPI API token for voxtype
EOF
            exit 0
            ;;
        *) error "Unknown option: $arg" ;;
    esac
done

# ─── Read versions ────────────────────────────────────────────────────
VOXTYPE_VERSION=$(python3.11 -c "
import re, pathlib
text = pathlib.Path('${VOXTYPE_DIR}/src/voxtype/__init__.py').read_text()
print(re.search(r'__version__\s*=\s*\"(.+?)\"', text).group(1))
")

OPENVIP_VERSION=$(python3.11 -c "
import re, pathlib
text = pathlib.Path('${OPENVIP_DIR}/pyproject.toml').read_text()
print(re.search(r'version\s*=\s*\"(.+?)\"', text).group(1))
")

# Check that voxtype's openvip dependency matches
OPENVIP_DEP_VERSION=$(python3.11 -c "
import re, pathlib
text = pathlib.Path('${VOXTYPE_DIR}/pyproject.toml').read_text()
m = re.search(r'\"openvip>=([^\"]+)\"', text)
print(m.group(1) if m else 'NOT FOUND')
")

printf "\n"
info "Versions"
printf "  voxtype:          %s\n" "$VOXTYPE_VERSION"
printf "  openvip:          %s\n" "$OPENVIP_VERSION"
printf "  openvip dep in voxtype: >=%s\n" "$OPENVIP_DEP_VERSION"
printf "\n"

# ─── Step 1: Tests ────────────────────────────────────────────────────
info "[1/5] Running voxtype tests..."
if [[ "$DRY_RUN" == true ]]; then
    warn "[dry-run] Would run: uv run --python 3.11 python -m pytest tests/ -x --tb=short"
else
    cd "$VOXTYPE_DIR"
    uv run --python 3.11 python -m pytest tests/ -x --tb=short || error "Tests failed. Fix before publishing."
    ok "All tests passed"
fi

# ─── Step 2: Lint ─────────────────────────────────────────────────────
info "[2/5] Running ruff..."
if [[ "$DRY_RUN" == true ]]; then
    warn "[dry-run] Would run: uv run --python 3.11 ruff check ."
else
    cd "$VOXTYPE_DIR"
    uv run --python 3.11 ruff check . || error "Lint errors. Fix before publishing."
    ok "Lint clean"
fi

# ─── Step 3: Build + publish openvip ──────────────────────────────────
info "[3/5] Build + publish openvip ${OPENVIP_VERSION}"

cd "$OPENVIP_DIR"
rm -rf dist/

info "Building openvip..."
uv build --sdist --wheel
ok "Built openvip: $(ls dist/)"

if [[ "$DRY_RUN" == true ]]; then
    warn "[dry-run] Would upload openvip to PyPI"
else
    if confirm "Upload openvip ${OPENVIP_VERSION} to PyPI?"; then
        PUBLISH_ARGS=""
        if [[ -n "${OPENVIP_PYPI_TOKEN:-}" ]]; then
            PUBLISH_ARGS="--token $OPENVIP_PYPI_TOKEN"
        fi
        uv publish $PUBLISH_ARGS
        ok "openvip ${OPENVIP_VERSION} published to PyPI"
    fi
fi

# ─── Step 4: Build + publish voxtype ─────────────────────────────────
info "[4/5] Build + publish voxtype ${VOXTYPE_VERSION}"

cd "$VOXTYPE_DIR"
rm -rf dist/

info "Building voxtype..."
uv build --sdist --wheel
ok "Built voxtype: $(ls dist/)"

# Verify the wheel doesn't contain local path references
if unzip -l dist/voxtype-*.whl 2>/dev/null | grep -q "nottoplay"; then
    error "Wheel contains local path reference to openvip! Check pyproject.toml."
fi
ok "Wheel is clean (no local path references)"

if [[ "$DRY_RUN" == true ]]; then
    warn "[dry-run] Would upload voxtype to PyPI"
else
    if confirm "Upload voxtype ${VOXTYPE_VERSION} to PyPI?"; then
        PUBLISH_ARGS=""
        if [[ -n "${VOXTYPE_PYPI_TOKEN:-}" ]]; then
            PUBLISH_ARGS="--token $VOXTYPE_PYPI_TOKEN"
        fi
        uv publish $PUBLISH_ARGS
        ok "voxtype ${VOXTYPE_VERSION} published to PyPI"
    fi
fi

# ─── Step 5: Git tag + GitHub release ─────────────────────────────────
info "[5/5] Git tag + GitHub release"

TAG="v${VOXTYPE_VERSION}"

if [[ "$DRY_RUN" == true ]]; then
    warn "[dry-run] Would create tag ${TAG} and GitHub release"
else
    if confirm "Create git tag ${TAG} and GitHub release?"; then
        cd "$VOXTYPE_DIR"
        git tag -a "$TAG" -m "Release ${TAG}"
        git push origin "$TAG"
        ok "Tag ${TAG} pushed"

        if command -v gh &>/dev/null; then
            gh release create "$TAG" \
                --title "voxtype ${VOXTYPE_VERSION}" \
                --notes "See [CHANGELOG.md](https://github.com/dragfly/voxtype/blob/main/CHANGELOG.md) for details." \
                --prerelease
            ok "GitHub release created"
        else
            warn "gh CLI not found — create the release manually on GitHub."
        fi
    fi
fi

printf "\n"
ok "Publish workflow complete!"
printf "\n"
printf "Verify:\n"
printf "  pip install voxtype==${VOXTYPE_VERSION}\n"
printf "  pip install openvip==${OPENVIP_VERSION}\n"
printf "\n"
