#!/bin/bash
# voxtype uninstaller
# Usage: ./uninstall.sh [--system]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
skip() { echo -e "[ ]  $1 (not found)"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Parse args
SYSTEM_WIDE=0
if [ "$1" = "--system" ]; then
    SYSTEM_WIDE=1
fi

if [ $SYSTEM_WIDE -eq 1 ]; then
    echo "voxtype uninstaller (system-wide)"
    BIN_DIR="/usr/local/bin"
else
    echo "voxtype uninstaller (user)"
    BIN_DIR="$HOME/.local/bin"
fi
echo "===================="

# Stop and remove ydotoold service
echo ""
echo "Removing ydotoold service..."
if [ $SYSTEM_WIDE -eq 1 ]; then
    if systemctl is-active --quiet ydotoold 2>/dev/null; then
        sudo systemctl stop ydotoold
        info "Stopped ydotoold"
    fi
    if [ -f /etc/systemd/system/ydotoold.service ]; then
        sudo systemctl disable ydotoold 2>/dev/null || true
        sudo rm /etc/systemd/system/ydotoold.service
        sudo systemctl daemon-reload
        info "Removed system service"
    else
        skip "System service"
    fi
else
    if systemctl --user is-active --quiet ydotoold 2>/dev/null; then
        systemctl --user stop ydotoold
        info "Stopped ydotoold"
    fi
    if [ -f ~/.config/systemd/user/ydotoold.service ]; then
        systemctl --user disable ydotoold 2>/dev/null || true
        rm ~/.config/systemd/user/ydotoold.service
        systemctl --user daemon-reload
        info "Removed user service"
    else
        skip "User service"
    fi
fi

# Remove binaries
echo ""
echo "Removing binaries from $BIN_DIR..."
if [ $SYSTEM_WIDE -eq 1 ]; then
    [ -f "$BIN_DIR/ydotool" ] && sudo rm "$BIN_DIR/ydotool" && info "Removed ydotool" || skip "ydotool"
    [ -f "$BIN_DIR/ydotoold" ] && sudo rm "$BIN_DIR/ydotoold" && info "Removed ydotoold" || skip "ydotoold"
else
    [ -f "$BIN_DIR/ydotool" ] && rm "$BIN_DIR/ydotool" && info "Removed ydotool" || skip "ydotool"
    [ -f "$BIN_DIR/ydotoold" ] && rm "$BIN_DIR/ydotoold" && info "Removed ydotoold" || skip "ydotoold"
fi

# Remove Python venv
echo ""
echo "Removing Python virtual environment..."
if [ -d "$SCRIPT_DIR/.venv" ]; then
    rm -rf "$SCRIPT_DIR/.venv"
    info "Removed .venv"
else
    skip ".venv"
fi

# Remove build artifacts
echo ""
echo "Removing build artifacts..."
rm -f "$SCRIPT_DIR/build/ydotool" "$SCRIPT_DIR/build/ydotoold" "$SCRIPT_DIR/build/evdev.whl" 2>/dev/null && info "Removed build artifacts" || skip "Build artifacts"

# Remove Docker images (optional)
echo ""
read -p "Remove Docker build images? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker rmi ydotool-builder evdev-builder 2>/dev/null && info "Removed Docker images" || skip "Docker images"
fi

# Done
echo ""
echo "===================="
info "Uninstall complete!"
echo ""
echo "Optional: ./remove-permissions.sh to undo system permissions"
echo "         (usually not needed, harmless to keep)"
