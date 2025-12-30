#!/bin/bash
# voxtype installer for macOS
# Usage: ./install-macos.sh [--mlx]

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
WITH_MLX=0
for arg in "$@"; do
    case $arg in
        --mlx) WITH_MLX=1 ;;
    esac
done

TOTAL=3
echo "voxtype installer (macOS)"
echo "============================"
[ $WITH_MLX -eq 1 ] && echo "MLX support: enabled (Apple Silicon GPU)"

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

# Install base + macos deps
uv sync --extra macos >/dev/null

if [ $WITH_MLX -eq 1 ]; then
    # Install mlx-whisper with --no-deps to avoid old numba/llvmlite conflict
    # Then install deps manually with modern versions
    uv pip install --no-deps mlx-whisper >/dev/null 2>&1
    uv pip install mlx mlx-audio huggingface-hub tqdm tiktoken "numba>=0.57" >/dev/null 2>&1
    info "Installed Python packages (with MLX for Apple Silicon GPU)"
else
    info "Installed Python packages (with pynput for hotkey detection)"
fi

# 3. Grant Accessibility permissions
step 3 "Checking permissions..."
echo ""
warn "macOS requires Accessibility permissions for keyboard simulation."
echo ""
echo "  To add your terminal app:"
echo ""
echo "  macOS Ventura/Sonoma (13+):"
echo "    1. Open System Settings"
echo "    2. Privacy & Security → Accessibility"
echo "    3. Click '+' at the bottom"
echo "    4. Navigate to /Applications/Utilities/ and select Terminal.app"
echo "       (or your terminal: iTerm, Alacritty, etc.)"
echo "    5. Enable the toggle next to the app"
echo ""
echo "  macOS Monterey and earlier (12-):"
echo "    1. Open System Preferences"
echo "    2. Security & Privacy → Privacy → Accessibility"
echo "    3. Click the lock at bottom left"
echo "    4. Click '+' and add your terminal"
echo ""
echo "  After adding permissions, RESTART your terminal."
echo ""

# Done
echo "===================="
info "Installation complete!"
echo ""
echo "Recommended keys for Mac (ScrollLock doesn't exist):"
echo "  --key KEY_RIGHTMETA   # Right Command (⌘) - RECOMMENDED"
echo "  --key KEY_RIGHTALT    # Right Option (⌥)"
echo ""
echo "NOTE: Avoid F1-F12, they produce escape sequences in terminal."
echo ""
echo "Example:"
echo "  uv run voxtype run --key KEY_RIGHTMETA --model base --enter"
echo ""
echo "With MLX (Apple Silicon GPU):"
echo "  uv run voxtype run --mlx --key KEY_RIGHTMETA --model large-v3 --enter"
