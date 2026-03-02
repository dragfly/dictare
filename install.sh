#!/usr/bin/env bash
# Dictare installer — voice-first control for AI coding agents
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/dragfly/dictare/main/install.sh | bash
#   bash install.sh [--gpu] [--skip-setup]
#
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
RESET='\033[0m'

info()  { printf "${GREEN}==>${RESET} ${BOLD}%s${RESET}\n" "$*"; }
ok()    { printf "${GREEN}==>${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}==>${RESET} %s\n" "$*"; }
error() { printf "${RED}ERROR:${RESET} %s\n" "$*" >&2; exit 1; }

# ─── Parse flags ───────────────────────────────────────────────────────────
INSTALL_GPU=false
SKIP_SETUP=false
for arg in "$@"; do
    case "$arg" in
        --gpu)         INSTALL_GPU=true ;;
        --skip-setup)  SKIP_SETUP=true ;;
        --help|-h)
            cat <<'EOF'
Dictare installer — voice-first control for AI coding agents

Usage:
  curl -fsSL https://raw.githubusercontent.com/dragfly/dictare/main/install.sh | bash
  bash install.sh [OPTIONS]

Options:
  --gpu          Enable CUDA GPU acceleration (Linux only)
  --skip-setup   Skip the first-time setup wizard
  --help         Show this help

macOS:  installs via Homebrew (brew install dragfly/tap/dictare)
Linux:  installs via uv tool install + systemd service
EOF
            exit 0
            ;;
        *) error "Unknown option: $arg. Use --help for usage." ;;
    esac
done

OS="$(uname -s)"
ARCH="$(uname -m)"

printf "\n"
info "Installing dictare ($OS $ARCH)"
printf "\n"

# ══════════════════════════════════════════════════════════════════════════════
# macOS — Homebrew
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$OS" == "Darwin" ]]; then
    if ! command -v brew &>/dev/null; then
        error "Homebrew is required on macOS.\nInstall it first: https://brew.sh"
    fi

    info "Adding dragfly tap..."
    brew tap dragfly/tap

    info "Installing dictare..."
    brew install dictare

    VERSION="$(dictare --version 2>&1)"
    ok "dictare installed: $VERSION"

    if [[ "$SKIP_SETUP" == false ]]; then
        printf "\n"
        info "Running first-time setup..."
        dictare setup
    fi

    printf "\n"
    ok "Done! Voice-control your AI agent:"
    printf "  ${BOLD}dictare agent claude${RESET}\n"
    printf "\n"
    exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
# Linux — uv tool install + systemd
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$OS" == "Linux" ]]; then
    if [[ "$EUID" -eq 0 ]]; then
        error "Do not run as root. The script will ask for sudo when needed."
    fi

    # ── System packages ─────────────────────────────────────────────────────
    if command -v apt-get &>/dev/null; then
        info "Installing system packages (sudo required)..."
        APPINDICATOR_PKG="gir1.2-appindicator3-0.1"
        if command -v lsb_release &>/dev/null; then
            _id=$(lsb_release -is 2>/dev/null || echo "")
            _rel=$(lsb_release -rs 2>/dev/null || echo "0")
            if [[ "$_id" == "Ubuntu" && "${_rel%%.*}" -ge 22 ]]; then
                APPINDICATOR_PKG="gir1.2-ayatanaappindicator3-0.1"
            fi
        fi
        sudo apt-get update -qq
        sudo apt-get install -y \
            libportaudio2 portaudio19-dev espeak-ng \
            "$APPINDICATOR_PKG" libgirepository-2.0-dev libcairo2-dev \
            build-essential pkg-config

    elif command -v dnf &>/dev/null; then
        info "Installing system packages (sudo required)..."
        sudo dnf install -y \
            portaudio portaudio-devel espeak-ng \
            libappindicator-gtk3 gobject-introspection-devel cairo-devel \
            gcc pkg-config

    elif command -v pacman &>/dev/null; then
        info "Installing system packages (sudo required)..."
        sudo pacman -S --noconfirm \
            portaudio espeak-ng libappindicator-gtk3 \
            gobject-introspection cairo base-devel pkg-config
    else
        warn "Unknown package manager — install portaudio and espeak-ng manually."
    fi

    # ── udev rule for hotkey ─────────────────────────────────────────────────
    UDEV_FILE="/etc/udev/rules.d/99-dictare.rules"
    if [[ ! -f "$UDEV_FILE" ]]; then
        info "Installing udev rule for hotkey access..."
        echo 'KERNEL=="event*", GROUP="input", MODE="0660"' | sudo tee "$UDEV_FILE" > /dev/null
        sudo udevadm control --reload-rules && sudo udevadm trigger
        ok "Hotkey udev rule installed"
    fi

    # ── uv ───────────────────────────────────────────────────────────────────
    if ! command -v uv &>/dev/null; then
        info "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
        command -v uv &>/dev/null || error "uv installation failed."
        ok "uv installed"
    else
        ok "uv found"
    fi

    # ── dictare ──────────────────────────────────────────────────────────────
    info "Installing dictare..."
    if [[ "$INSTALL_GPU" == true ]]; then
        uv tool install --python 3.11 "dictare[gpu]"
    else
        uv tool install --python 3.11 dictare
    fi

    # ── PATH ─────────────────────────────────────────────────────────────────
    mkdir -p "$HOME/.local/bin"
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        warn "'~/.local/bin' not in PATH. Add to ~/.bashrc or ~/.zshrc:"
        printf "    export PATH=\"\$HOME/.local/bin:\$PATH\"\n\n"
        export PATH="$HOME/.local/bin:$PATH"
    fi

    # ── PyGObject (tray icon) ────────────────────────────────────────────────
    info "Installing PyGObject (tray icon)..."
    DICTARE_PYTHON="$(uv tool dir)/dictare/bin/python"
    if [[ -f "$DICTARE_PYTHON" ]]; then
        "$DICTARE_PYTHON" -m pip install --quiet PyGObject pycairo 2>/dev/null || \
            warn "PyGObject install failed — tray icon may not work."
        ok "PyGObject installed"
    fi

    # ── systemd service ──────────────────────────────────────────────────────
    info "Installing systemd service..."
    dictare service install

    info "Starting dictare engine..."
    dictare service start

    VERSION="$(dictare --version 2>&1)"
    ok "dictare installed: $VERSION"

    if [[ "$SKIP_SETUP" == false ]]; then
        printf "\n"
        info "Running first-time setup..."
        dictare setup
    fi

    printf "\n"
    ok "Done! Voice-control your AI agent:"
    printf "  ${BOLD}dictare agent claude${RESET}\n"
    printf "\n"
    exit 0
fi

error "Unsupported OS: $OS"
