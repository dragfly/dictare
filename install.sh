#!/usr/bin/env bash
# Dictare installer --voice-first control for AI coding agents
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
DIM='\033[2m'
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
Dictare installer --voice-first control for AI coding agents

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
# macOS --Homebrew
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
# Linux --uv tool install + systemd
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$OS" == "Linux" ]]; then
    if [[ "$EUID" -eq 0 ]]; then
        error "Do not run as root. Run as your normal user."
    fi

    # ══════════════════════════════════════════════════════════════════════════
    # Phase 1: Check prerequisites (no sudo, no changes)
    # ══════════════════════════════════════════════════════════════════════════
    MISSING_PKGS=()
    INSTALL_CMD=""
    HAS_PREREQS=false

    # ── Check system packages ────────────────────────────────────────────────
    if command -v dpkg &>/dev/null; then
        # Debian/Ubuntu
        APPINDICATOR_PKG="gir1.2-appindicator3-0.1"
        if command -v lsb_release &>/dev/null; then
            _id=$(lsb_release -is 2>/dev/null || echo "")
            _rel=$(lsb_release -rs 2>/dev/null || echo "0")
            if [[ "$_id" == "Ubuntu" && "${_rel%%.*}" -ge 22 ]]; then
                APPINDICATOR_PKG="gir1.2-ayatanaappindicator3-0.1"
            fi
        fi

        REQUIRED_PKGS=(
            libportaudio2 portaudio19-dev espeak-ng ydotool
            "$APPINDICATOR_PKG" libgirepository-2.0-dev libcairo2-dev
            build-essential pkg-config
        )
        for pkg in "${REQUIRED_PKGS[@]}"; do
            if ! dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
                MISSING_PKGS+=("$pkg")
            fi
        done

        if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
            INSTALL_CMD="sudo apt-get update && sudo apt-get install -y ${MISSING_PKGS[*]}"
        fi

    elif command -v rpm &>/dev/null; then
        # Fedora/RHEL
        REQUIRED_PKGS=(
            portaudio portaudio-devel espeak-ng ydotool
            libappindicator-gtk3 gobject-introspection-devel cairo-devel
            gcc pkg-config
        )
        for pkg in "${REQUIRED_PKGS[@]}"; do
            if ! rpm -q "$pkg" &>/dev/null; then
                MISSING_PKGS+=("$pkg")
            fi
        done

        if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
            INSTALL_CMD="sudo dnf install -y ${MISSING_PKGS[*]}"
        fi

    elif command -v pacman &>/dev/null; then
        # Arch
        REQUIRED_PKGS=(
            portaudio espeak-ng ydotool libappindicator-gtk3
            gobject-introspection cairo base-devel pkg-config
        )
        for pkg in "${REQUIRED_PKGS[@]}"; do
            if ! pacman -Q "$pkg" &>/dev/null; then
                MISSING_PKGS+=("$pkg")
            fi
        done

        if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
            INSTALL_CMD="sudo pacman -S --noconfirm ${MISSING_PKGS[*]}"
        fi
    else
        warn "Unknown package manager. You'll need to install dependencies manually."
        warn "Required: portaudio, espeak-ng, ydotool, AppIndicator GI typelib"
    fi

    # ── Check udev rule, input group, ydotoold ──────────────────────────────
    UDEV_FILE="/etc/udev/rules.d/99-dictare.rules"
    NEED_UDEV=false
    NEED_INPUT_GROUP=false
    NEED_YDOTOOLD=false

    [[ ! -f "$UDEV_FILE" ]] && NEED_UDEV=true
    groups | grep -qw input || NEED_INPUT_GROUP=true
    if command -v ydotoold &>/dev/null; then
        systemctl is-active ydotoold &>/dev/null 2>&1 || NEED_YDOTOOLD=true
    fi

    # ── Report and exit if prerequisites are missing ─────────────────────────
    if [[ ${#MISSING_PKGS[@]} -gt 0 || "$NEED_UDEV" == true || "$NEED_INPUT_GROUP" == true || "$NEED_YDOTOOLD" == true ]]; then
        printf "\n"
        warn "Some prerequisites are missing. Run these commands, then re-run this script:"

        # Box drawing helpers --64-char content width, auto-padded
        _boxtop()   { printf "  ${DIM}┌──────────────────────────────────────────────────────────────────┐${RESET}\n"; }
        _boxbot()   { printf "  ${DIM}└──────────────────────────────────────────────────────────────────┘${RESET}\n"; }
        _boxtitle() { printf "  ${DIM}│${RESET} ${BOLD}%-64s${RESET} ${DIM}│${RESET}\n" "$1"; }
        _boxline()  { printf "  ${DIM}│${RESET} %-64s ${DIM}│${RESET}\n" "$1"; }
        _boxgap()   { printf "  ${DIM}│${RESET} %-64s ${DIM}│${RESET}\n" ""; }

        if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
            printf "\n"
            _boxtop
            _boxtitle "System packages"
            _boxgap
            _boxline "Installs libraries and tools that dictare needs:"
            _boxline "  portaudio    -- audio capture from your microphone"
            _boxline "  espeak-ng    -- text-to-speech fallback engine"
            _boxline "  ydotool      -- types text into other apps (keyboard mode)"
            _boxline "  AppIndicator -- system tray icon on Wayland/GNOME"
            _boxline "  build tools  -- needed to compile Python bindings for the"
            _boxline "                 tray icon (PyGObject)"
            _boxbot
            printf "\n"
            printf "  ${BOLD}%s${RESET}\n" "$INSTALL_CMD"
        fi

        if [[ "$NEED_UDEV" == true ]]; then
            printf "\n"
            _boxtop
            _boxtitle "Udev rule"
            _boxgap
            _boxline "Creates a system rule that lets your user read keyboard"
            _boxline "input devices and /dev/uinput without being root."
            _boxline "Needed for the global hotkey and for ydotool to type text."
            _boxbot
            printf "\n"
            printf "  ${BOLD}printf 'KERNEL==\"event*\", GROUP=\"input\", MODE=\"0660\"\\nKERNEL==\"uinput\", GROUP=\"input\", MODE=\"0660\"\\n' | sudo tee /etc/udev/rules.d/99-dictare.rules > /dev/null && sudo udevadm control --reload-rules && sudo udevadm trigger${RESET}\n"
        fi

        if [[ "$NEED_INPUT_GROUP" == true ]]; then
            printf "\n"
            _boxtop
            _boxtitle "Input group"
            _boxgap
            _boxline "Adds your user to the 'input' group. This is required for"
            _boxline "the global hotkey -- dictare reads keyboard events to detect"
            _boxline "when you press the activation key."
            _boxgap
            _boxline "Log out and back in after running this command."
            _boxbot
            printf "\n"
            printf "  ${BOLD}sudo usermod -aG input \$USER${RESET}\n"
        fi

        if [[ "$NEED_YDOTOOLD" == true ]]; then
            printf "\n"
            _boxtop
            _boxtitle "ydotoold daemon"
            _boxgap
            _boxline "Starts the ydotool background service. This is what allows"
            _boxline "dictare to type transcribed text into any application."
            _boxbot
            printf "\n"
            printf "  ${BOLD}sudo systemctl enable ydotoold && sudo systemctl start ydotoold${RESET}\n"
        fi

        printf "\n"
        exit 1
    fi

    ok "All system prerequisites satisfied"

    # ══════════════════════════════════════════════════════════════════════════
    # Phase 2: Install (user-space only, no sudo needed)
    # ══════════════════════════════════════════════════════════════════════════

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

    # ── PATH check ───────────────────────────────────────────────────────────
    mkdir -p "$HOME/.local/bin"
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        printf "\n"
        warn "~/.local/bin is not in your PATH. Add it to your shell profile:"
        printf "\n"
        printf "  ${BOLD}export PATH=\"\$HOME/.local/bin:\$PATH\"${RESET}\n"
        printf "\n"
        printf "  ${DIM}Add this line to your ~/.bashrc or ~/.zshrc, then restart your shell.${RESET}\n"
        printf "\n"
        export PATH="$HOME/.local/bin:$PATH"
    fi

    # ── PyGObject (tray icon, required for Wayland) ──────────────────────────
    info "Installing PyGObject (tray icon)..."
    DICTARE_PYTHON="$(uv tool dir)/dictare/bin/python"
    if [[ -f "$DICTARE_PYTHON" ]]; then
        if uv pip install --python "$DICTARE_PYTHON" PyGObject pycairo 2>/dev/null; then
            ok "PyGObject installed"
        else
            warn "PyGObject install failed --tray icon may not work on Wayland."
            printf "  ${DIM}On X11 the tray works without PyGObject.${RESET}\n"
        fi
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
