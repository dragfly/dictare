#!/bin/bash
#
# voxtype installer
#
# Usage:
#   Local:   ./install.sh [--dev]
#   Remote:  curl -fsSL https://raw.githubusercontent.com/dragfly/voxtype/main/install.sh | sh
#   Uninstall: ./install.sh uninstall
#
set -e

VERSION="2.27.5"
REPO_URL="https://github.com/dragfly/voxtype"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${GREEN}✓${NC} $1"; }
warn()    { echo -e "${YELLOW}!${NC} $1"; }
error()   { echo -e "${RED}✗${NC} $1"; exit 1; }
step()    { echo -e "\n${BLUE}→${NC} ${BOLD}$1${NC}"; }
banner()  { echo -e "\n${BOLD}$1${NC}\n$2"; }

# Detect environment
OS="$(uname -s)"
ARCH="$(uname -m)"
IS_LOCAL=0
DEV_MODE=0

# Detect if running from local repo
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" 2>/dev/null)" && pwd 2>/dev/null || echo "")"
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    IS_LOCAL=1
fi

# Parse arguments
ACTION="install"
FORCE_MODE=0
GPU_MODE=0
for arg in "$@"; do
    case $arg in
        uninstall|remove) ACTION="uninstall" ;;
        --dev) DEV_MODE=1 ;;
        --force) FORCE_MODE=1 ;;
        --gpu) GPU_MODE=1 ;;
        --help|-h) ACTION="help" ;;
    esac
done

#####################################################################
# HELP
#####################################################################
show_help() {
    cat << EOF
voxtype installer v${VERSION}

Usage:
  ./install.sh              Install voxtype globally (uv tool)
  ./install.sh --gpu        Install with GPU support (Linux: CUDA, macOS: MLX)
  ./install.sh --force      Force rebuild from source (ignore cache)
  ./install.sh --dev        Install in development mode (editable, in .venv)
  ./install.sh uninstall    Remove voxtype and dependencies
  curl ... | sh             Install from remote

Options:
  --gpu       Install with GPU acceleration (cuDNN on Linux, MLX on macOS)
  --force     Force rebuild from source, even if same version (for developers)
  --dev       Development mode: creates .venv with editable install
  uninstall   Remove voxtype, ydotool service, and cleanup

What gets installed:
  - voxtype command (via uv tool or .venv)
  - ydotool + ydotoold (Linux only, for keyboard simulation)
  - System dependencies (portaudio, etc.)

GPU support:
  Linux:  --gpu installs nvidia-cudnn-cu12 (requires CUDA 12 drivers)
  macOS:  --gpu installs mlx-whisper (Apple Silicon only, auto-enabled)
EOF
    exit 0
}

#####################################################################
# UNINSTALL
#####################################################################
do_uninstall() {
    banner "voxtype uninstaller" "========================"

    step "Removing voxtype..."

    # Remove uv tool installation
    if command -v uv &>/dev/null && uv tool list 2>/dev/null | grep -q voxtype; then
        uv tool uninstall voxtype 2>/dev/null || true
        info "Removed voxtype (uv tool)"
    fi

    # Remove pipx installation
    if command -v pipx &>/dev/null && pipx list 2>/dev/null | grep -q voxtype; then
        pipx uninstall voxtype 2>/dev/null || true
        info "Removed voxtype (pipx)"
    fi

    # Remove local .venv if in repo
    if [ $IS_LOCAL -eq 1 ] && [ -d "$SCRIPT_DIR/.venv" ]; then
        rm -rf "$SCRIPT_DIR/.venv"
        info "Removed .venv"
    fi

    # Linux: remove ydotoold service
    if [ "$OS" = "Linux" ]; then
        step "Removing ydotoold service..."

        if systemctl --user is-active --quiet ydotoold 2>/dev/null; then
            systemctl --user stop ydotoold 2>/dev/null || true
            info "Stopped ydotoold"
        fi

        if [ -f "$HOME/.config/systemd/user/ydotoold.service" ]; then
            systemctl --user disable ydotoold 2>/dev/null || true
            rm -f "$HOME/.config/systemd/user/ydotoold.service"
            systemctl --user daemon-reload 2>/dev/null || true
            info "Removed ydotoold service"
        fi

        # Remove ydotool binaries
        if [ -f "$HOME/.local/bin/ydotool" ]; then
            rm -f "$HOME/.local/bin/ydotool" "$HOME/.local/bin/ydotoold"
            info "Removed ydotool binaries"
        fi
    fi

    # Remove build artifacts if in repo
    if [ $IS_LOCAL -eq 1 ]; then
        step "Cleaning build artifacts..."
        rm -f "$SCRIPT_DIR/build/ydotool" "$SCRIPT_DIR/build/ydotoold" 2>/dev/null || true
        rm -f "$SCRIPT_DIR/build/evdev-"*.whl 2>/dev/null || true
        info "Cleaned build artifacts"
    fi

    echo ""
    info "Uninstall complete!"
    echo ""
    echo "Note: System packages (portaudio, etc.) were not removed."
    echo "      User permissions (input group) were not changed."
}

#####################################################################
# INSTALL UV
#####################################################################
ensure_uv() {
    if command -v uv &>/dev/null; then
        return 0
    fi

    step "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add to PATH for this session
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    if ! command -v uv &>/dev/null; then
        error "Failed to install uv. Please install manually: https://docs.astral.sh/uv/"
    fi
    info "Installed uv"
}

#####################################################################
# macOS INSTALL
#####################################################################
install_macos() {
    banner "voxtype installer" "macOS $([ "$ARCH" = "arm64" ] && echo "(Apple Silicon)" || echo "(Intel)")"

    # 1. Install uv
    ensure_uv

    # 2. Install system deps
    step "Installing system dependencies..."
    if command -v brew &>/dev/null; then
        brew list portaudio &>/dev/null || brew install portaudio
        info "portaudio ready"
    else
        warn "Homebrew not found. Install portaudio manually if audio fails."
    fi

    # 3. Install voxtype
    if [ $DEV_MODE -eq 1 ]; then
        step "Installing voxtype (development mode)..."
        cd "$SCRIPT_DIR"

        # Use mlx extra on Apple Silicon
        if [ "$ARCH" = "arm64" ]; then
            uv sync --python 3.11 --extra mlx
        else
            uv sync --python 3.11
        fi
        info "Created .venv with editable install"

        echo ""
        echo "Development mode active. Run with:"
        echo -e "  ${BOLD}source .venv/bin/activate${NC}"
        echo -e "  ${BOLD}voxtype listen${NC}"
        echo ""
        echo "Or without activating:"
        echo -e "  ${BOLD}uv run voxtype listen${NC}"
    else
        step "Installing voxtype..."

        # Build install flags
        # --reinstall: upgrade even if installed
        # --force: rebuild from source (ignore cached wheel)
        # --prerelease=allow: needed for mlx-audio 0.3.0 which requires transformers==5.0.0rc3
        INSTALL_FLAGS="--reinstall --python 3.11 --prerelease=allow"
        if [ $FORCE_MODE -eq 1 ]; then
            INSTALL_FLAGS="$INSTALL_FLAGS --force"
        fi

        if [ $IS_LOCAL -eq 1 ]; then
            # Local install from repo
            if [ "$ARCH" = "arm64" ]; then
                uv tool install $INSTALL_FLAGS "$SCRIPT_DIR[mlx,tray]"
            else
                uv tool install $INSTALL_FLAGS "$SCRIPT_DIR[tray]"
            fi
        else
            # Remote install from PyPI
            if [ "$ARCH" = "arm64" ]; then
                uv tool install $INSTALL_FLAGS "voxtype[mlx,tray]"
            else
                uv tool install $INSTALL_FLAGS "voxtype[tray]"
            fi
        fi
        info "Installed voxtype"

        echo ""
        echo -e "Run: ${BOLD}voxtype listen${NC}"
    fi

    # 4. Permissions reminder
    step "Permissions required"
    echo ""
    warn "macOS requires Accessibility permission for keyboard simulation."
    echo ""
    echo -e "  1. Open ${BOLD}System Settings → Privacy & Security → Accessibility${NC}"
    echo "  2. Click '+' and add your terminal app"
    echo "  3. Enable the toggle"
    echo -e "  4. ${BOLD}Restart your terminal${NC}"
    echo ""
}

#####################################################################
# LINUX INSTALL
#####################################################################
install_linux() {
    banner "voxtype installer" "Linux ($ARCH)"

    # 1. Install uv
    ensure_uv

    # 2. Install system deps
    step "Checking system dependencies..."

    MISSING_DEPS=""

    # Check for portaudio
    if ! ldconfig -p 2>/dev/null | grep -q libportaudio; then
        MISSING_DEPS="portaudio"
    fi

    # Check for input group
    if ! groups | grep -q '\binput\b'; then
        MISSING_DEPS="$MISSING_DEPS input-group"
    fi

    if [ -n "$MISSING_DEPS" ]; then
        warn "Some system dependencies may be missing: $MISSING_DEPS"
        echo ""
        echo "  Install with:"
        if command -v apt &>/dev/null; then
            echo "    sudo apt install libportaudio2 portaudio19-dev"
            echo "    sudo usermod -aG input \$USER"
        elif command -v pacman &>/dev/null; then
            echo "    sudo pacman -S portaudio"
            echo "    sudo usermod -aG input \$USER"
        elif command -v dnf &>/dev/null; then
            echo "    sudo dnf install portaudio portaudio-devel"
            echo "    sudo usermod -aG input \$USER"
        fi
        echo ""
        echo "  Then log out and back in."
        echo ""
    else
        info "System dependencies OK"
    fi

    # 3. Install/build ydotool
    step "Setting up ydotool..."

    BIN_DIR="$HOME/.local/bin"
    mkdir -p "$BIN_DIR"

    # Check if ydotool already installed
    if command -v ydotool &>/dev/null; then
        info "ydotool already installed"
    else
        # Try to install from package manager
        if command -v apt &>/dev/null; then
            if apt-cache show ydotool &>/dev/null; then
                echo "  Installing ydotool via apt..."
                sudo apt install -y ydotool
                info "Installed ydotool from apt"
            fi
        elif command -v pacman &>/dev/null; then
            echo "  Installing ydotool via pacman..."
            sudo pacman -S --noconfirm ydotool
            info "Installed ydotool from pacman"
        fi

        # Fallback: build from source if Docker available
        if ! command -v ydotool &>/dev/null && [ $IS_LOCAL -eq 1 ]; then
            if command -v docker &>/dev/null && [ -f "$SCRIPT_DIR/build/Dockerfile.ydotool" ]; then
                echo "  Building ydotool from source..."
                docker build -q -f "$SCRIPT_DIR/build/Dockerfile.ydotool" -t ydotool-builder "$SCRIPT_DIR/build/" >/dev/null
                docker run --rm ydotool-builder cat /ydotool > "$BIN_DIR/ydotool"
                docker run --rm ydotool-builder cat /ydotoold > "$BIN_DIR/ydotoold"
                chmod +x "$BIN_DIR/ydotool" "$BIN_DIR/ydotoold"
                info "Built ydotool from source"
            else
                warn "ydotool not found. Install manually: sudo apt install ydotool"
            fi
        fi
    fi

    # 4. Setup ydotoold service
    if command -v ydotool &>/dev/null || [ -f "$BIN_DIR/ydotoold" ]; then
        step "Setting up ydotoold service..."

        YDOTOOLD_PATH="$(command -v ydotoold 2>/dev/null || echo "$BIN_DIR/ydotoold")"

        mkdir -p "$HOME/.config/systemd/user"
        cat > "$HOME/.config/systemd/user/ydotoold.service" << EOF
[Unit]
Description=ydotool daemon

[Service]
ExecStart=$YDOTOOLD_PATH
Restart=on-failure

[Install]
WantedBy=default.target
EOF

        systemctl --user daemon-reload
        systemctl --user enable ydotoold &>/dev/null || true
        systemctl --user start ydotoold &>/dev/null || true

        if systemctl --user is-active --quiet ydotoold; then
            info "ydotoold service running"
        else
            warn "ydotoold service created but not running. Start with: systemctl --user start ydotoold"
        fi
    fi

    # 5. Install voxtype
    if [ $DEV_MODE -eq 1 ]; then
        step "Installing voxtype (development mode)..."
        cd "$SCRIPT_DIR"

        if [ $GPU_MODE -eq 1 ]; then
            uv sync --python 3.11 --extra gpu
        else
            uv sync --python 3.11
        fi

        # Install pre-built evdev if available
        if ls "$SCRIPT_DIR/build/evdev-"*.whl &>/dev/null; then
            uv pip install --reinstall "$SCRIPT_DIR/build/evdev-"*.whl 2>/dev/null || true
        fi

        info "Created .venv with editable install"

        echo ""
        echo "Development mode active. Run with:"
        echo -e "  ${BOLD}source .venv/bin/activate${NC}"
        echo -e "  ${BOLD}voxtype listen${NC}"
        echo ""
        echo "Or without activating:"
        echo -e "  ${BOLD}uv run voxtype listen${NC}"
    else
        step "Installing voxtype..."

        # Build install flags
        # --reinstall: upgrade even if installed
        # --python 3.11: consistent Python version across platforms
        # --force: rebuild from source (ignore cached wheel)
        # --prerelease=allow: needed for mlx-audio 0.3.0 which requires transformers==5.0.0rc3
        INSTALL_FLAGS="--reinstall --python 3.11 --prerelease=allow"
        if [ $FORCE_MODE -eq 1 ]; then
            INSTALL_FLAGS="$INSTALL_FLAGS --force"
        fi

        # Determine package spec (with or without gpu extra, always include tray)
        if [ $IS_LOCAL -eq 1 ]; then
            if [ $GPU_MODE -eq 1 ]; then
                PKG_SPEC="$SCRIPT_DIR[gpu,tray]"
            else
                PKG_SPEC="$SCRIPT_DIR[tray]"
            fi
        else
            if [ $GPU_MODE -eq 1 ]; then
                PKG_SPEC="voxtype[gpu,tray]"
            else
                PKG_SPEC="voxtype[tray]"
            fi
        fi

        uv tool install $INSTALL_FLAGS "$PKG_SPEC"
        info "Installed voxtype"

        echo ""
        echo -e "Run: ${BOLD}voxtype listen${NC}"
    fi

    echo ""
}

#####################################################################
# MAIN
#####################################################################
main() {
    case $ACTION in
        help) show_help ;;
        uninstall) do_uninstall ;;
        install)
            case $OS in
                Darwin) install_macos ;;
                Linux)  install_linux ;;
                *) error "Unsupported OS: $OS" ;;
            esac

            echo ""
            info "Installation complete!"
            echo ""
            ;;
    esac
}

main
