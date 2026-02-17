#!/usr/bin/env bash
# Voxtype Linux development install script.
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
Voxtype Linux development install script.

Usage: ./scripts/linux-install.sh [--gpu]

Options:
  --gpu      Install CUDA support for GPU-accelerated Whisper
  --help     Show this help

What happens:
  1. Installs system packages (apt/dnf/pacman) — requires sudo
  2. Installs uv (Python package manager)
  3. Creates Python venv + installs PyGObject for tray icon
  4. Installs voxtype from local source via uv sync
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
info "This script will install voxtype for Linux development."
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
if command -v apt-get &>/dev/null; then
    PKG_MGR="apt"
    PACKAGES=(
        # Audio
        libportaudio2 portaudio19-dev
        # TTS fallback
        espeak-ng
        # Tray icon — GObject introspection typelibs (runtime)
        gir1.2-appindicator3-0.1
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

# ─── 5. Install PyGObject for tray icon ────────────────────────────────
info "Installing PyGObject (tray icon support)..."
uv pip install PyGObject pycairo

# Verify gi is accessible
if "$VENV_DIR/bin/python" -c "import gi; gi.require_version('AppIndicator3', '0.1')" 2>/dev/null; then
    ok "PyGObject + AppIndicator3 working"
else
    warn "AppIndicator3 not available. Tray icon may not work."
fi

# ─── 6. Install voxtype from source ────────────────────────────────────
info "Installing voxtype from source..."

# Stop existing service first
if systemctl --user is-active voxtype.service &>/dev/null; then
    info "Stopping existing service..."
    systemctl --user stop voxtype.service
fi
"$VENV_DIR/bin/python" -m voxtype tray stop 2>/dev/null || true

# Sync dependencies
if [[ "$INSTALL_GPU" == true ]]; then
    info "Installing with GPU (CUDA) support..."
    uv sync --extra gpu --extra tts
else
    uv sync --extra tts
fi

# Verify installation
VERSION=$("$VENV_DIR/bin/python" -m voxtype --version 2>&1 || echo "unknown")
ok "voxtype installed: $VERSION"

# ─── 7. Install systemd service ────────────────────────────────────────
info "Installing systemd user service..."

SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_DIR/voxtype.service" << EOF
[Unit]
Description=Voxtype Engine — voice-first control for AI coding agents
After=network.target

[Service]
Type=simple
ExecStart=$VENV_DIR/bin/python -m voxtype engine start --foreground
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable voxtype.service
ok "systemd service installed"

# ─── 8. Start engine ───────────────────────────────────────────────────
info "Starting voxtype engine..."
systemctl --user start voxtype.service

# Wait a moment for startup
sleep 2

if systemctl --user is-active voxtype.service &>/dev/null; then
    ok "Engine running"
else
    warn "Engine may have failed to start. Check: journalctl --user -u voxtype.service"
fi

# ─── 9. Summary ────────────────────────────────────────────────────────
printf "\n"
ok "Done! Voxtype is installed and running."
printf "\n"
printf "  ${BOLD}voxtype agent claude${RESET}    # voice-control Claude Code\n"
printf "  ${BOLD}voxtype tray start${RESET}      # show tray icon\n"
printf "\n"
printf "Service commands:\n"
printf "  ${BOLD}systemctl --user status voxtype${RESET}\n"
printf "  ${BOLD}journalctl --user -u voxtype -f${RESET}   # follow logs\n"
printf "\n"

if [[ "$HAS_NVIDIA" == true && "$INSTALL_GPU" == false ]]; then
    printf "${YELLOW}Tip:${RESET} Re-run with --gpu to enable CUDA acceleration.\n\n"
fi
