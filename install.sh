#!/bin/bash
# claude-mic installer (no sudo required)
# Usage: ./install.sh [--system]

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
if [ "$1" = "--system" ]; then
    SYSTEM_WIDE=1
    TOTAL=5
    echo "claude-mic installer (system-wide, requires sudo)"
    BIN_DIR="/usr/local/bin"
else
    TOTAL=5
    echo "claude-mic installer (user-level, no sudo)"
    BIN_DIR="$HOME/.local/bin"
fi
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
if [ -d .venv ] && ! .venv/bin/python --version 2>/dev/null | grep -q "3\.11"; then
    rm -rf .venv
fi
uv sync >/dev/null
uv pip install build/evdev-*.whl >/dev/null
info "Installed Python packages"

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
echo "Run: uv run claude-mic run"
