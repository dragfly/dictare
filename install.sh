#!/usr/bin/env bash
# Dictare installer — voice-first control for AI coding agents
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/dragfly/dictare/main/install.sh | bash
#   bash install.sh [OPTIONS]
#
# Modelled after: https://ollama.com/install.sh
set -euo pipefail

REPO_URL="https://github.com/dragfly/dictare"

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
Dictare installer — voice-first control for AI coding agents

Usage:
  curl -fsSL https://raw.githubusercontent.com/dragfly/dictare/main/install.sh | bash
  bash install.sh [OPTIONS]

Options:
  --skip-setup   Install dictare only, skip the 'dictare setup' wizard
  --uninstall    Remove dictare
  --help, -h     Show this help

What happens:
  1. Installs uv (Python package manager) if missing
  2. Installs dictare via 'uv tool install'
  3. Downloads models, installs background service, configures permissions
  4. Ready — run 'dictare agent claude'
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
    info "Uninstalling dictare..."
    if command -v dictare &>/dev/null; then
        dictare service stop 2>/dev/null || true
        dictare tray stop 2>/dev/null || true
    fi
    if command -v uv &>/dev/null; then
        uv tool uninstall dictare 2>/dev/null || true
    fi
    ok "dictare uninstalled."
    exit 0
fi

# ─── Install ───────────────────────────────────────────────────────────
printf "\n"
info "Installing dictare for $PLATFORM ($ARCH)"
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

# 4. Install dictare
info "Installing dictare..."

# On Apple Silicon, include mlx extra for hardware-accelerated inference
EXTRAS=""
if [[ "$PLATFORM" == "macOS" && "$ARCH" == "arm64" ]]; then
    EXTRAS="[mlx]"
fi

uv tool install --python 3.11 --prerelease=allow "dictare${EXTRAS}"
ok "dictare installed: $(dictare --version 2>&1 || echo '(version check failed)')"

# 5. Run setup wizard
if [[ "$SKIP_SETUP" == true ]]; then
    warn "Skipping setup (--skip-setup). Run 'dictare setup' when ready."
else
    printf "\n"
    info "Running first-time setup..."
    dictare setup
fi

printf "\n"
ok "Done! Launch an agent:"
printf "  ${BOLD}dictare agent claude${RESET}    # voice-control Claude Code\n"
printf "  ${BOLD}dictare agent cursor${RESET}    # voice-control Cursor\n"
printf "\n"
printf "Optional — monitor engine from the menu bar:\n"
printf "  ${BOLD}dictare tray start${RESET}\n"
printf "\n"
