#!/usr/bin/env bash
# Dictare Linux development install script.
# Installs all system dependencies + builds from local source.
#
# Usage: ./scripts/linux-install.sh [--gpu]
#
# Options:
#   --gpu    Install CUDA support for GPU-accelerated inference
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

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
INSTALL_GPU=false
for arg in "$@"; do
    case "$arg" in
        --gpu) INSTALL_GPU=true ;;
        --help|-h)
            cat <<'EOF'
Dictare Linux development install script.

Usage: ./scripts/linux-install.sh [--gpu]

Options:
  --gpu      Install CUDA support for GPU-accelerated Whisper
  --help     Show this help

What happens:
  1. Installs system packages (apt/dnf/pacman) — requires sudo
  2. Installs uv (Python package manager)
  3. Creates Python venv + installs PyGObject for tray icon
  4. Installs dictare from local source via uv sync
  5. Installs systemd user service
  6. Starts the engine
EOF
            exit 0
            ;;
        *) error "Unknown option: $arg. Use --help for usage." ;;
    esac
done

# ─── Check we're on Linux ──────────────────────────────────────────────
if [[ "$(uname -s)" != "Linux" ]]; then
    error "This script is for Linux only. Use ./scripts/macos-install.sh on macOS."
fi

# ─── Check we're NOT running as root ───────────────────────────────────
if [[ "$EUID" -eq 0 ]]; then
    error "Do not run this script as root or with sudo. The script will ask for sudo when needed."
fi

cd "$PROJECT_DIR"

# ─── Explain what we're about to do ────────────────────────────────────
printf "\n"
info "This script will install dictare for Linux development."
printf "\n"
printf "What happens:\n"
printf "  1. Install system packages via apt/dnf/pacman ${YELLOW}(requires sudo)${RESET}\n"
printf "  2. Install uv (Python package manager)\n"
printf "  3. Create Python venv and install dependencies\n"
printf "  4. Install systemd user service\n"
printf "  5. Start the engine\n"
printf "\n"

# ─── 1. Install system dependencies ────────────────────────────────────
info "Installing system dependencies (sudo required)..."

# Detect package manager
PKG_MGR=""
if command -v apt-get &>/dev/null; then
    PKG_MGR="apt"

    # Ubuntu 22.04+ renamed AppIndicator to AyatanaAppIndicator
    APPINDICATOR_PKG="gir1.2-appindicator3-0.1"
    if command -v lsb_release &>/dev/null; then
        _distro_id=$(lsb_release -is 2>/dev/null || echo "")
        _distro_rel=$(lsb_release -rs 2>/dev/null || echo "0")
        if [[ "$_distro_id" == "Ubuntu" && "${_distro_rel%%.*}" -ge 22 ]]; then
            APPINDICATOR_PKG="gir1.2-ayatanaappindicator3-0.1"
        fi
    fi

    PACKAGES=(
        # Audio
        libportaudio2 portaudio19-dev
        # TTS fallback
        espeak-ng
        # Tray icon — GObject introspection typelibs (runtime)
        "$APPINDICATOR_PKG"
        # Tray icon — PyGObject build dependencies (compile for Python 3.11)
        libgirepository-2.0-dev libcairo2-dev
        # Build tools
        build-essential pkg-config
    )
    sudo apt-get update
    sudo apt-get install -y "${PACKAGES[@]}"
elif command -v dnf &>/dev/null; then
    PKG_MGR="dnf"
    PACKAGES=(
        # Audio
        portaudio portaudio-devel
        # TTS fallback
        espeak-ng
        # Tray icon — GObject introspection typelibs
        libappindicator-gtk3
        # PyGObject build dependencies
        gobject-introspection-devel cairo-devel
        # Build tools
        gcc pkg-config
    )
    sudo dnf install -y "${PACKAGES[@]}"
elif command -v pacman &>/dev/null; then
    PKG_MGR="pacman"
    PACKAGES=(
        # Audio
        portaudio
        # TTS fallback
        espeak-ng
        # Tray icon — GObject introspection typelibs
        libappindicator-gtk3
        # PyGObject build dependencies
        gobject-introspection cairo
        # Build tools
        base-devel pkg-config
    )
    sudo pacman -S --noconfirm "${PACKAGES[@]}"
else
    warn "Unknown package manager. Install manually:"
    printf "  - portaudio (audio capture)\n"
    printf "  - espeak-ng (TTS fallback)\n"
    printf "  - python3-gi + gir1.2-appindicator3-0.1 (tray icon)\n"
fi

ok "System dependencies installed"

# ─── 1b. Install udev rule for evdev hotkey support ────────────────────
# evdev reads /dev/input/event* which requires the 'input' group by default.
# A udev rule grants access without requiring a re-login.
if [[ "$PKG_MGR" != "" ]]; then
    UDEV_RULE='KERNEL=="event*", GROUP="input", MODE="0660"'
    UDEV_FILE="/etc/udev/rules.d/99-dictare.rules"
    if [[ ! -f "$UDEV_FILE" ]]; then
        info "Installing udev rule for hotkey access..."
        echo "$UDEV_RULE" | sudo tee "$UDEV_FILE" > /dev/null
        sudo udevadm control --reload-rules
        sudo udevadm trigger
        ok "Hotkey udev rule installed (no re-login needed)"
    else
        ok "Hotkey udev rule already present"
    fi
fi

# ─── 2. Check for NVIDIA GPU ───────────────────────────────────────────
HAS_NVIDIA=false
if command -v nvidia-smi &>/dev/null; then
    if nvidia-smi &>/dev/null; then
        HAS_NVIDIA=true
        GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
        ok "NVIDIA GPU detected: $GPU_NAME"
    fi
fi

if [[ "$HAS_NVIDIA" == true && "$INSTALL_GPU" == false ]]; then
    warn "GPU detected but --gpu not specified. Whisper will run on CPU."
    printf "  Re-run with: ./scripts/linux-install.sh --gpu\n\n"
fi

# ─── 3. Install uv if missing ──────────────────────────────────────────
if command -v uv &>/dev/null; then
    ok "uv found: $(uv --version)"
else
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        error "uv installation failed. Install manually: https://docs.astral.sh/uv/"
    fi
    ok "uv installed"
fi

# ─── 4. Create/update venv ─────────────────────────────────────────────
info "Setting up Python environment..."

VENV_DIR="$PROJECT_DIR/.venv"

if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating venv..."
    uv venv --python 3.11 "$VENV_DIR"
fi

ok "Python venv ready"

# ─── 5. Install dictare + sync dependencies ───────────────────────────
info "Installing dictare from source..."

# Stop existing service first
if systemctl --user is-active dictare.service &>/dev/null; then
    info "Stopping existing service..."
    systemctl --user stop dictare.service
fi
"$VENV_DIR/bin/python" -m dictare tray stop 2>/dev/null || true

# Sync dependencies — use --frozen to avoid modifying uv.lock on Linux
if [[ "$INSTALL_GPU" == true ]]; then
    info "Installing with GPU (CUDA) support..."
    uv sync --frozen --extra gpu
else
    uv sync --frozen
fi

# ─── 6. Install PyGObject for tray icon ────────────────────────────────
# Must be AFTER uv sync, otherwise uv sync removes it
info "Installing PyGObject (tray icon support)..."
uv pip install PyGObject pycairo

# Verify gi is accessible — try AyatanaAppIndicator3 first (Ubuntu 22.04+), then AppIndicator3
if "$VENV_DIR/bin/python" - << 'PYEOF' 2>/dev/null
import gi, sys
for ns in ("AyatanaAppIndicator3", "AppIndicator3"):
    try:
        gi.require_version(ns, "0.1")
        sys.exit(0)
    except ValueError:
        pass
sys.exit(1)
PYEOF
then
    ok "PyGObject + AppIndicator working"
else
    warn "AppIndicator not available. Tray icon may not work."
fi

# Verify installation
VERSION=$("$VENV_DIR/bin/python" -m dictare --version 2>&1 || echo "unknown")
ok "dictare installed: $VERSION"

# ─── Symlink to ~/.local/bin so 'dictare' works from any shell ─────────
mkdir -p "$HOME/.local/bin"
ln -sf "$VENV_DIR/bin/dictare" "$HOME/.local/bin/dictare"
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    warn "'~/.local/bin' is not in your PATH."
    printf "  Add this to your ~/.bashrc or ~/.zshrc:\n"
    printf "    export PATH=\"\$HOME/.local/bin:\$PATH\"\n\n"
fi
ok "dictare symlinked to ~/.local/bin/dictare"

# ─── 7. Install systemd service ────────────────────────────────────────
info "Installing systemd user service..."
# Delegate to dictare service install — generates the correct unit file
# (ExecStart, env vars, Restart=always) for the current version.
"$VENV_DIR/bin/dictare" service install
ok "systemd service installed"

# ─── 8. Start engine ───────────────────────────────────────────────────
info "Starting dictare engine..."
"$VENV_DIR/bin/dictare" service start

# Wait a moment for startup
sleep 2

if systemctl --user is-active dictare.service &>/dev/null; then
    ok "Engine running"
else
    warn "Engine may have failed to start. Check: journalctl --user -u dictare.service"
fi

# ─── 9. Summary ────────────────────────────────────────────────────────
printf "\n"
ok "Done! Dictare is installed and running."
printf "\n"
printf "  ${BOLD}dictare agent claude${RESET}    # voice-control Claude Code\n"
printf "  ${BOLD}dictare tray start${RESET}      # show tray icon\n"
printf "\n"
printf "Service commands:\n"
printf "  ${BOLD}systemctl --user status dictare${RESET}\n"
printf "  ${BOLD}journalctl --user -u dictare -f${RESET}   # follow logs\n"
printf "\n"

if [[ "$HAS_NVIDIA" == true && "$INSTALL_GPU" == false ]]; then
    printf "${YELLOW}Tip:${RESET} Re-run with --gpu to enable CUDA acceleration.\n\n"
fi
