#!/usr/bin/env bash
# Voxtype installer — voice-first control for AI coding agents
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/dragfly/voxtype/main/install.sh | bash
#   bash install.sh [OPTIONS]
#
# Modelled after: https://ollama.com/install.sh
set -euo pipefail

REPO_URL="https://github.com/dragfly/voxtype"

# ─── Helpers ───────────────────────────────────────────────────────────
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
RESET='\033[0m'

info()  { printf "${GREEN}==>${RESET} ${BOLD}%s${RESET}\n" "$*"; }
ok()    { printf "${GREEN}==>${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}==>${RESET} %s\n" "$*"; }
error() { printf "${RED}ERROR:${RESET} %s\n" "$*" >&2; exit 1; }

# ─── Parse flags ───────────────────────────────────────────────────────
SKIP_SETUP=false
UNINSTALL=false
for arg in "$@"; do
    case "$arg" in
        --help|-h)
            cat <<'EOF'
Voxtype installer — voice-first control for AI coding agents

Usage:
  curl -fsSL https://raw.githubusercontent.com/dragfly/voxtype/main/install.sh | bash
  bash install.sh [OPTIONS]

Options:
  --skip-setup   Install voxtype only, skip the 'voxtype setup' wizard
  --uninstall    Remove voxtype
  --help, -h     Show this help

What happens:
  1. Installs uv (Python package manager) if missing
  2. Installs voxtype via 'uv tool install'
  3. Downloads models, installs background service, configures permissions
  4. Ready — run 'voxtype agent claude'
EOF
            exit 0
            ;;
        --skip-setup) SKIP_SETUP=true ;;
        --uninstall)  UNINSTALL=true ;;
        *) error "Unknown option: $arg. Use --help for usage." ;;
    esac
done

# ─── Detect OS ─────────────────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"
case "$OS" in
    Darwin) PLATFORM="macOS" ;;
    Linux)  PLATFORM="Linux" ;;
    *)      error "Unsupported OS: $OS (only macOS and Linux are supported)" ;;
esac

# ─── Uninstall ─────────────────────────────────────────────────────────
if [[ "$UNINSTALL" == true ]]; then
    info "Uninstalling voxtype..."
    if command -v voxtype &>/dev/null; then
        voxtype service stop 2>/dev/null || true
        voxtype tray stop 2>/dev/null || true
    fi
    if command -v uv &>/dev/null; then
        uv tool uninstall voxtype 2>/dev/null || true
    fi
    ok "voxtype uninstalled."
    exit 0
fi

# ─── Install ───────────────────────────────────────────────────────────
printf "\n"
info "Installing voxtype for $PLATFORM ($ARCH)"
printf "\n"

# 1. Check system audio library
if [[ "$PLATFORM" == "Linux" ]]; then
    if ! ldconfig -p 2>/dev/null | grep -q libportaudio; then
        warn "portaudio not found — audio may not work."
        printf "  Install with: sudo apt install libportaudio2 portaudio19-dev\n\n"
    fi
fi

# 3. Install uv if missing
if command -v uv &>/dev/null; then
    ok "uv found"
else
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        error "uv installation failed. Install manually: https://docs.astral.sh/uv/"
    fi
    ok "uv installed"
fi

# 4. Install voxtype
info "Installing voxtype..."

# On Apple Silicon, include mlx extra for hardware-accelerated inference
EXTRAS=""
if [[ "$PLATFORM" == "macOS" && "$ARCH" == "arm64" ]]; then
    EXTRAS="[mlx]"
fi

uv tool install --python 3.11 --prerelease=allow "voxtype${EXTRAS}"
ok "voxtype installed: $(voxtype --version 2>&1 || echo '(version check failed)')"

# 5. Run setup wizard
if [[ "$SKIP_SETUP" == true ]]; then
    warn "Skipping setup (--skip-setup). Run 'voxtype setup' when ready."
else
    printf "\n"
    info "Running first-time setup..."
    voxtype setup
fi

printf "\n"
ok "Done! Launch an agent:"
printf "  ${BOLD}voxtype agent claude${RESET}    # voice-control Claude Code\n"
printf "  ${BOLD}voxtype agent cursor${RESET}    # voice-control Cursor\n"
printf "\n"
printf "Optional — monitor engine from the menu bar:\n"
printf "  ${BOLD}voxtype tray start${RESET}\n"
printf "\n"
