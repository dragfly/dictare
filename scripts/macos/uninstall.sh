#!/usr/bin/env bash
# Dictare macOS uninstall — full cleanup for testing fresh installs.
#
# PRESERVES by default:
#   ~/.config/dictare/      (config.toml — your settings)
#   ~/.local/share/dictare/ (logs, models, sessions, stats, tts-cache)
#
# Use --wipe-config to also remove config and data.
#
# REMOVES everything else: Homebrew install, launchd service, .app bundle,
# TCC permissions, ~/.dictare runtime state, dev venv, uv tool install.
#
set -euo pipefail

WIPE_CONFIG=false
for arg in "$@"; do
    case "$arg" in
        --wipe-config) WIPE_CONFIG=true ;;
        -h|--help)
            echo "Usage: $0 [--wipe-config]"
            echo "  --wipe-config  Also remove ~/.config/dictare/ and ~/.local/share/dictare/"
            exit 0
            ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
RESET='\033[0m'

ok()   { printf "${GREEN}==>${RESET} %s\n" "$*"; }
info() { printf "${GREEN}==>${RESET} ${BOLD}%s${RESET}\n" "$*"; }
warn() { printf "${YELLOW}==>${RESET} %s\n" "$*"; }
skip() { printf "    ${YELLOW}skip${RESET} %s\n" "$*"; }
gone() { printf "    ${GREEN}gone${RESET} %s\n" "$*"; }

if [[ "$(uname -s)" != "Darwin" ]]; then
    printf "${RED}ERROR:${RESET} This script is for macOS only.\n" >&2
    exit 1
fi

printf "\n"
info "Dictare macOS uninstall"
if $WIPE_CONFIG; then
    printf "\n  ${RED}--wipe-config:${RESET} config and data will also be removed\n"
fi
printf "\n"

# ── 1. Stop services ────────────────────────────────────────────────────────
info "Stopping services..."

for dictare_bin in \
    "$(brew --prefix 2>/dev/null)/bin/dictare" \
    "$HOME/.local/bin/dictare" \
    "$(command -v dictare 2>/dev/null || true)"
do
    if [[ -n "$dictare_bin" && -x "$dictare_bin" ]]; then
        "$dictare_bin" tray stop 2>/dev/null && ok "Tray stopped" || true
        "$dictare_bin" service stop 2>/dev/null && ok "Service stopped" || true
        break
    fi
done

pkill -f "Dictare.app/Contents/MacOS/Dictare" 2>/dev/null || true
pkill -f "dictare serve" 2>/dev/null || true
pkill -f "dictare.tray" 2>/dev/null || true
sleep 1

# ── 2. Unload and remove launchd plist ──────────────────────────────────────
info "Removing launchd service..."
for plist in \
    "$HOME/Library/LaunchAgents/dev.dragfly.dictare.plist" \
    "$HOME/Library/LaunchAgents/dev.dragfly.dictare.tray.plist"
do
    if [[ -f "$plist" ]]; then
        launchctl unload "$plist" 2>/dev/null || true
        rm -f "$plist"
        gone "$plist"
    else
        skip "$plist (not found)"
    fi
done

# ── 3. Remove .app bundle ──────────────────────────────────────────────────
info "Removing app bundle..."
APP="$HOME/Applications/Dictare.app"
if [[ -d "$APP" ]]; then
    rm -rf "$APP"
    gone "$APP"
else
    skip "$APP (not found)"
fi

# ── 4. Homebrew uninstall ───────────────────────────────────────────────────
if command -v brew &>/dev/null && brew list dictare &>/dev/null 2>&1; then
    info "Uninstalling via Homebrew..."
    brew uninstall dictare 2>&1
    ok "Homebrew: dictare removed"
else
    skip "Homebrew: dictare not installed"
fi

# ── 5. uv tool uninstall (in case installed via uv tool install) ────────────
if command -v uv &>/dev/null && uv tool list 2>/dev/null | grep -q "^dictare"; then
    info "Removing uv tool install..."
    uv tool uninstall dictare 2>&1
    ok "uv tool: dictare removed"
else
    skip "uv tool: dictare not installed"
fi

# ── 6. Remove stale symlinks ───────────────────────────────────────────────
if [[ -L "$HOME/.local/bin/dictare" ]]; then
    rm "$HOME/.local/bin/dictare"
    gone "~/.local/bin/dictare"
fi

# ── 7. Remove ~/.dictare runtime state (python_path, status files) ──────────
info "Removing runtime state..."
if [[ -d "$HOME/.dictare" ]]; then
    rm -rf "$HOME/.dictare"
    gone "~/.dictare"
else
    skip "~/.dictare (not found)"
fi

# ── 8. Reset TCC permissions ───────────────────────────────────────────────
info "Resetting macOS permissions..."
tccutil reset ListenEvent dev.dragfly.dictare 2>/dev/null || true
ok "Input Monitoring reset"
tccutil reset Accessibility dev.dragfly.dictare 2>/dev/null || true
ok "Accessibility reset"
tccutil reset Microphone dev.dragfly.dictare 2>/dev/null || true
ok "Microphone reset"
# Legacy bundle ID (pre-v0.1.135)
tccutil reset ListenEvent com.dragfly.dictare 2>/dev/null || true
tccutil reset Accessibility com.dragfly.dictare 2>/dev/null || true
tccutil reset Microphone com.dragfly.dictare 2>/dev/null || true

# ── 9. Remove dev venv if inside a dictare repo ────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
if [[ -d "$PROJECT_DIR/.venv" && -f "$PROJECT_DIR/pyproject.toml" ]]; then
    if grep -q 'name = "dictare"' "$PROJECT_DIR/pyproject.toml" 2>/dev/null; then
        rm -rf "$PROJECT_DIR/.venv"
        gone "$PROJECT_DIR/.venv"
    fi
fi

# ── 10. Optionally remove config and data ───────────────────────────────────
if $WIPE_CONFIG; then
    info "Removing config and data..."
    for dir in "$HOME/.config/dictare" "$HOME/.local/share/dictare"; do
        if [[ -d "$dir" ]]; then
            rm -rf "$dir"
            gone "$dir"
        else
            skip "$dir (not found)"
        fi
    done
fi

# ── Summary ─────────────────────────────────────────────────────────────────
printf "\n"
ok "Uninstall complete."
printf "\n"
if ! $WIPE_CONFIG; then
    printf "  ${YELLOW}Preserved:${RESET}\n"
    printf "    ~/.config/dictare/      (config.toml)\n"
    printf "    ~/.local/share/dictare/ (logs, models, sessions, stats)\n"
    printf "\n"
    printf "  To also remove config and data:\n"
    printf "    ${BOLD}$0 --wipe-config${RESET}\n"
fi
printf "\n"
printf "  To reinstall:\n"
printf "    ${BOLD}./scripts/macos/install.sh${RESET}\n"
printf "\n"
