#!/bin/bash
# voxtype installer - auto-detects platform
# Usage: ./install.sh [--mlx] [--gpu] [--system]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
fail() { echo -e "${RED}[✗]${NC} $1"; exit 1; }
step() { echo -e "\n${GREEN}[$1/$TOTAL]${NC} $2"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Parse args
SYSTEM_WIDE=0
WITH_GPU=0
WITH_MLX=0
for arg in "$@"; do
    case $arg in
        --system) SYSTEM_WIDE=1 ;;
        --gpu) WITH_GPU=1 ;;
        --mlx) WITH_MLX=1 ;;
    esac
done

# Auto-detect platform
if [[ "$(uname)" == "Darwin" ]]; then
    #############################################
    # macOS Installation
    #############################################

    # Auto-detect Apple Silicon and enable MLX
    if [[ "$(uname -m)" == "arm64" ]]; then
        WITH_MLX=1
        info "Detected Apple Silicon - enabling MLX"
    fi

    TOTAL=3
    echo "voxtype installer (macOS)"
    echo "============================"
    [ $WITH_MLX -eq 1 ] && echo "MLX support: enabled (Apple Silicon GPU)"

    # Check prerequisites
    command -v uv >/dev/null || fail "uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"

    # 1. Install system dependencies
    step 1 "Installing system dependencies..."
    if command -v brew >/dev/null; then
        brew list portaudio >/dev/null 2>&1 || brew install portaudio
        info "portaudio installed"
    else
        warn "Homebrew not found. Install portaudio manually: brew install portaudio"
    fi

    # 2. Install Python dependencies
    step 2 "Installing Python dependencies..."
    # MLX requires Python 3.12 (torch doesn't have 3.13 wheels yet)
    if [ -d .venv ]; then
        rm -rf .venv
    fi

    # Install dependencies with Python 3.11 for MLX compatibility (torch 2.0.1 only has cp311 wheels)
    if [ $WITH_MLX -eq 1 ]; then
        uv sync --python 3.11 --extra macos --extra mlx >/dev/null
        info "Installed Python packages (with MLX for Apple Silicon GPU)"
    else
        uv sync --extra macos >/dev/null
        info "Installed Python packages"
    fi

    # 3. Grant Accessibility permissions
    step 3 "Checking permissions..."
    echo ""
    warn "macOS requires Accessibility permissions for keyboard simulation."
    echo ""
    echo "  To add your terminal app:"
    echo ""
    echo "  1. Open System Settings → Privacy & Security → Accessibility"
    echo "  2. Click '+' and add your terminal (Terminal, iTerm, Alacritty, etc.)"
    echo "  3. Enable the toggle next to the app"
    echo "  4. RESTART your terminal"
    echo ""

    # Done
    echo "===================="
    info "Installation complete!"
    echo ""
    echo "Run: uv run voxtype run --vad"
    echo ""
    if [ $WITH_MLX -eq 1 ]; then
        echo "MLX is auto-detected, no need for --mlx flag!"
    fi

else
    #############################################
    # Linux Installation
    #############################################

    TOTAL=5
    if [ $SYSTEM_WIDE -eq 1 ]; then
        echo "voxtype installer (Linux, system-wide, requires sudo)"
        BIN_DIR="/usr/local/bin"
    else
        echo "voxtype installer (Linux, user-level, no sudo)"
        BIN_DIR="$HOME/.local/bin"
    fi
    [ $WITH_GPU -eq 1 ] && echo "GPU support: enabled"
    echo "===================="

    # Check prerequisites
    command -v docker >/dev/null || fail "Docker not found. Install Docker first."
    command -v uv >/dev/null || fail "uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"

    # 1. Build ydotool
    step 1 "Building ydotool from source..."
    docker build -q -f build/Dockerfile.ydotool -t ydotool-builder build/ >/dev/null
    docker run --rm ydotool-builder cat /ydotool > build/ydotool
    docker run --rm ydotool-builder cat /ydotoold > build/ydotoold
    chmod +x build/ydotool build/ydotoold
    info "Built ydotool v1.0.4"

    # 2. Build evdev
    step 2 "Building evdev wheel..."
    rm -f build/evdev-*.whl build/evdev.whl
    docker build -q -f build/Dockerfile.evdev -t evdev-builder build/ >/dev/null
    docker run --rm -v "$SCRIPT_DIR/build:/output" evdev-builder
    info "Built evdev wheel"

    # 3. Install binaries
    step 3 "Installing binaries to $BIN_DIR..."
    if [ $SYSTEM_WIDE -eq 1 ]; then
        sudo mkdir -p "$BIN_DIR"
        sudo cp build/ydotool build/ydotoold "$BIN_DIR/"
    else
        mkdir -p "$BIN_DIR"
        cp build/ydotool build/ydotoold "$BIN_DIR/"
    fi
    info "Installed ydotool, ydotoold"

    # 4. Set up ydotoold service
    step 4 "Setting up ydotoold service..."
    if [ $SYSTEM_WIDE -eq 1 ]; then
        sudo tee /etc/systemd/system/ydotoold.service >/dev/null << EOF
[Unit]
Description=ydotool daemon

[Service]
ExecStart=$BIN_DIR/ydotoold
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
        sudo systemctl daemon-reload
        sudo systemctl enable ydotoold >/dev/null 2>&1
        info "Created systemd system service"
    else
        mkdir -p ~/.config/systemd/user
        cat > ~/.config/systemd/user/ydotoold.service << EOF
[Unit]
Description=ydotool daemon

[Service]
ExecStart=$BIN_DIR/ydotoold
Restart=on-failure

[Install]
WantedBy=default.target
EOF
        systemctl --user daemon-reload
        systemctl --user enable ydotoold >/dev/null 2>&1
        info "Created systemd user service"
    fi

    # 5. Install Python dependencies
    step 5 "Installing Python dependencies..."
    # Remove old venv if Python version is wrong
    if [ -d .venv ] && ! .venv/bin/python --version 2>/dev/null | grep -q "3\.1[123]"; then
        rm -rf .venv
    fi
    # Always include linux extras on Linux (for evdev from PyPI as fallback)
    EXTRAS="--extra linux"
    [ $WITH_GPU -eq 1 ] && EXTRAS="$EXTRAS --extra gpu"

    uv sync $EXTRAS >/dev/null

    # Prefer our pre-built evdev wheel (compatible with Python 3.11)
    uv pip install --reinstall build/evdev-*.whl >/dev/null 2>&1 || true

    if [ $WITH_GPU -eq 1 ]; then
        info "Installed Python packages (with GPU/CUDA support)"
    else
        info "Installed Python packages"
    fi

    # Check system dependencies
    echo ""
    MISSING=""
    dpkg -s libportaudio2 >/dev/null 2>&1 || MISSING="libportaudio2"
    groups | grep -q '\binput\b' || MISSING="$MISSING input-group"

    # Done
    echo "===================="
    info "Installation complete!"
    echo ""

    if [ -n "$MISSING" ]; then
        warn "System permissions needed (run once):"
        echo "    ./setup-permissions.sh"
        echo ""
        echo "Then log out/in and start the daemon:"
    else
        echo "Start the daemon:"
    fi

    if [ $SYSTEM_WIDE -eq 1 ]; then
        echo "    sudo systemctl start ydotoold"
    else
        echo "    systemctl --user start ydotoold"
    fi
    echo ""
    echo "Run: uv run voxtype run"
fi
