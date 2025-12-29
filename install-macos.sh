#!/bin/bash
# claude-mic installer for macOS

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
fail() { echo -e "${RED}[✗]${NC} $1"; exit 1; }
step() { echo -e "\n${GREEN}[$1/$TOTAL]${NC} $2"; }

TOTAL=3
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "claude-mic installer (macOS)"
echo "============================"

# Check prerequisites
command -v uv >/dev/null || fail "uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"

# Check macOS
if [[ "$(uname)" != "Darwin" ]]; then
    fail "This script is for macOS only. Use ./install.sh for Linux."
fi

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
# Remove old venv if Python version is wrong
if [ -d .venv ] && ! .venv/bin/python --version 2>/dev/null | grep -q "3\.11"; then
    rm -rf .venv
fi
uv sync --extra macos >/dev/null
info "Installed Python packages (with pynput for hotkey detection)"

# 3. Grant Accessibility permissions
step 3 "Checking permissions..."
echo ""
warn "macOS requires Accessibility permissions for keyboard simulation."
echo ""
echo "  1. Open System Preferences → Security & Privacy → Privacy"
echo "  2. Select 'Accessibility' in the left panel"
echo "  3. Add Terminal (or your terminal app) to the list"
echo "  4. Restart your terminal"
echo ""

# Done
echo "===================="
info "Installation complete!"
echo ""
echo "Run: uv run claude-mic run"
