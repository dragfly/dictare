#!/usr/bin/env bash
# Dictare macOS uninstall — full cleanup for testing fresh installs.
#
# PRESERVES:
#   ~/.config/dictare/     (config.toml — your settings)
#   ~/.local/share/dictare/ (logs, models, sessions, stats, tts-cache)
#
# REMOVES everything else: Homebrew install, launchd service, Swift launcher,
# dev venv, tray pid, any uv tool install.
#
set -euo pipefail

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
printf "\n"
printf "  ${YELLOW}Preserving:${RESET} ~/.config/dictare/ and ~/.local/share/dictare/\n"
printf "\n"

# ── 1. Stop tray and service ───────────────────────────────────────────────
info "Stopping services..."

# Stop tray (try both installed and uv tool locations)
for dictare_bin in \
    "$(brew --prefix 2>/dev/null)/bin/dictare" \
    "$HOME/.local/bin/dictare" \
    "$(command -v dictare 2>/dev/null || true)"
do
    if [[ -x "$dictare_bin" ]]; then
        "$dictare_bin" tray stop 2>/dev/null && ok "Tray stopped" || true
        "$dictare_bin" service stop 2>/dev/null && ok "Service stopped" || true
        "$dictare_bin" service uninstall 2>/dev/null && ok "Service uninstalled" || true
        break
    fi
done

# Kill any remaining dictare processes
pkill -f "dictare serve" 2>/dev/null && warn "Killed lingering dictare processes" || true

# ── 2. Remove launchd plist directly (belt and suspenders) ────────────────
PLIST="$HOME/Library/LaunchAgents/dev.dragfly.dictare.plist"
if [[ -f "$PLIST" ]]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    gone "$PLIST"
else
    skip "$PLIST (not found)"
fi

# ── 3. Remove Swift launcher app ──────────────────────────────────────────
SWIFT_APP="$HOME/Applications/Dictare.app"
if [[ -d "$SWIFT_APP" ]]; then
    rm -rf "$SWIFT_APP"
    gone "$SWIFT_APP"
else
    skip "$SWIFT_APP (not found)"
fi

# ── 4. Homebrew uninstall ─────────────────────────────────────────────────
if command -v brew &>/dev/null && brew list dictare &>/dev/null 2>&1; then
    info "Uninstalling via Homebrew..."
    brew uninstall dictare 2>&1
    ok "Homebrew: dictare removed"
else
    skip "Homebrew: dictare not installed"
fi

# ── 5. uv tool uninstall (in case installed via uv tool install) ──────────
if command -v uv &>/dev/null && uv tool list 2>/dev/null | grep -q "^dictare"; then
    info "Removing uv tool install..."
    uv tool uninstall dictare 2>&1
    ok "uv tool: dictare removed"
else
    skip "uv tool: dictare not installed"
fi

# ── 6. Remove ~/.local/bin symlink ────────────────────────────────────────
if [[ -L "$HOME/.local/bin/dictare" ]]; then
    rm "$HOME/.local/bin/dictare"
    gone "~/.local/bin/dictare"
fi

# ── 7. Remove tray.pid (stale after uninstall) ────────────────────────────
TRAY_PID="$HOME/.local/share/dictare/tray.pid"
if [[ -f "$TRAY_PID" ]]; then
    rm -f "$TRAY_PID"
    gone "~/.local/share/dictare/tray.pid"
fi

# ── 8. Remove ~/.dictare if it exists (legacy location) ───────────────────
if [[ -d "$HOME/.dictare" ]]; then
    rm -rf "$HOME/.dictare"
    gone "~/.dictare"
fi

# ── 9. Remove dev venv if inside a dictare repo ───────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
if [[ -d "$PROJECT_DIR/.venv" && -f "$PROJECT_DIR/pyproject.toml" ]]; then
    if grep -q 'name = "dictare"' "$PROJECT_DIR/pyproject.toml" 2>/dev/null; then
        rm -rf "$PROJECT_DIR/.venv"
        gone "$PROJECT_DIR/.venv"
    fi
fi

printf "\n"
ok "Uninstall complete."
printf "\n"
printf "  ${YELLOW}Preserved:${RESET}\n"
printf "    ~/.config/dictare/      (config.toml)\n"
printf "    ~/.local/share/dictare/ (logs, models, sessions, stats)\n"
printf "\n"
printf "  To remove config and data too (full wipe):\n"
printf "    rm -rf ~/.config/dictare ~/.local/share/dictare\n"
printf "\n"
printf "  To reinstall:\n"
printf "    ${BOLD}./scripts/install.sh${RESET}  (dev)\n"
printf "    ${BOLD}curl -fsSL https://raw.githubusercontent.com/dragfly/dictare/main/install.sh | bash${RESET}\n"
printf "\n"
