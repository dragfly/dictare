#!/usr/bin/env bash
# Dictare Linux uninstall — full cleanup for testing fresh installs.
#
# PRESERVES:
#   ~/.config/dictare/     (config.toml — your settings)
#   ~/.local/share/dictare/ (logs, models, sessions, stats, tts-cache)
#
# REMOVES everything else: uv tool install, systemd service, udev rule,
# dev venv, symlinks, any lingering processes.
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

if [[ "$(uname -s)" != "Linux" ]]; then
    printf "${RED}ERROR:${RESET} This script is for Linux only.\n" >&2
    exit 1
fi

if [[ "$EUID" -eq 0 ]]; then
    printf "${RED}ERROR:${RESET} Do not run as root. The script will ask for sudo when needed.\n" >&2
    exit 1
fi

printf "\n"
info "Dictare Linux uninstall"
printf "\n"
printf "  ${YELLOW}Preserving:${RESET} ~/.config/dictare/ and ~/.local/share/dictare/\n"
printf "\n"

# ── 1. Stop tray and service ───────────────────────────────────────────────
info "Stopping services..."

for dictare_bin in \
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

# ── 2. Remove systemd unit directly (belt and suspenders) ─────────────────
UNIT_FILE="$HOME/.config/systemd/user/dictare.service"
if [[ -f "$UNIT_FILE" ]]; then
    systemctl --user stop dictare.service 2>/dev/null || true
    systemctl --user disable dictare.service 2>/dev/null || true
    rm -f "$UNIT_FILE"
    systemctl --user daemon-reload 2>/dev/null || true
    gone "$UNIT_FILE"
else
    skip "$UNIT_FILE (not found)"
fi

# ── 3. uv tool uninstall ──────────────────────────────────────────────────
if command -v uv &>/dev/null && uv tool list 2>/dev/null | grep -q "^dictare"; then
    info "Removing uv tool install..."
    uv tool uninstall dictare 2>&1
    ok "uv tool: dictare removed"
else
    skip "uv tool: dictare not installed"
fi

# ── 4. Remove ~/.local/bin symlink ────────────────────────────────────────
if [[ -L "$HOME/.local/bin/dictare" ]]; then
    rm "$HOME/.local/bin/dictare"
    gone "~/.local/bin/dictare"
elif [[ -f "$HOME/.local/bin/dictare" ]]; then
    rm "$HOME/.local/bin/dictare"
    gone "~/.local/bin/dictare (binary)"
else
    skip "~/.local/bin/dictare (not found)"
fi

# ── 5. Remove udev rule ───────────────────────────────────────────────────
UDEV_FILE="/etc/udev/rules.d/99-dictare.rules"
if [[ -f "$UDEV_FILE" ]]; then
    info "Removing udev rule (sudo required)..."
    sudo rm -f "$UDEV_FILE"
    sudo udevadm control --reload-rules 2>/dev/null || true
    gone "$UDEV_FILE"
else
    skip "$UDEV_FILE (not found)"
fi

# ── 6. Remove tray.pid (stale after uninstall) ────────────────────────────
TRAY_PID="$HOME/.local/share/dictare/tray.pid"
if [[ -f "$TRAY_PID" ]]; then
    rm -f "$TRAY_PID"
    gone "~/.local/share/dictare/tray.pid"
fi

# ── 7. Remove ~/.dictare if it exists (legacy location) ───────────────────
if [[ -d "$HOME/.dictare" ]]; then
    rm -rf "$HOME/.dictare"
    gone "~/.dictare"
fi

# ── 8. Remove dev venv if inside a dictare repo ───────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
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
printf "    ${BOLD}./scripts/linux-install.sh${RESET}  (dev)\n"
printf "    ${BOLD}curl -fsSL https://raw.githubusercontent.com/dragfly/dictare/main/install.sh | bash${RESET}\n"
printf "\n"
