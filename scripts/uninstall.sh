#!/usr/bin/env bash
# Uninstall Dictare runtime/service integration while preserving config/models.
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RESET='\033[0m'

ok()   { printf "${GREEN}==>${RESET} %s\n" "$*"; }
info() { printf "${GREEN}==>${RESET} ${BOLD}%s${RESET}\n" "$*"; }
skip() { printf "    ${YELLOW}skip${RESET} %s\n" "$*"; }
gone() { printf "    ${GREEN}moved${RESET} %s\n" "$*"; }

TRASH="$HOME/.dictare/trash/uninstall.$(date +%Y%m%d%H%M%S)"

move_path() {
    local path="$1"
    if [[ ! -e "$path" && ! -L "$path" ]]; then
        skip "$path (not found)"
        return
    fi
    mkdir -p "$TRASH"
    local base
    base="$(basename "$path")"
    local dest="$TRASH/$base"
    local i=0
    while [[ -e "$dest" || -L "$dest" ]]; do
        i=$((i + 1))
        dest="$TRASH/$base.$i"
    done
    mv "$path" "$dest"
    gone "$path -> $dest"
}

printf "\n"
info "Uninstalling Dictare runtime"
printf "\n"
printf "  ${YELLOW}Preserving:${RESET}\n"
printf "    ~/.config/dictare/                 config\n"
printf "    ~/.local/share/dictare/models/     downloaded models\n"
printf "    ~/.local/share/dictare/sessions/   sessions\n"
printf "    ~/.local/share/dictare/stats/      stats\n"
printf "\n"

DICTARE_BIN="$HOME/.local/bin/dictare"
if [[ -x "$DICTARE_BIN" ]]; then
    "$DICTARE_BIN" tray stop 2>/dev/null || true
    "$DICTARE_BIN" service stop 2>/dev/null || true
    "$DICTARE_BIN" service uninstall 2>/dev/null || true
fi

if command -v uv &>/dev/null && uv tool list 2>/dev/null | grep -q "^dictare"; then
    info "Removing legacy uv tool install"
    uv tool uninstall dictare || true
fi

case "$(uname -s)" in
    Darwin)
        launchctl unload "$HOME/Library/LaunchAgents/dev.dragfly.dictare.tray.plist" 2>/dev/null || true
        launchctl unload "$HOME/Library/LaunchAgents/dev.dragfly.dictare.plist" 2>/dev/null || true
        move_path "$HOME/Library/LaunchAgents/dev.dragfly.dictare.tray.plist"
        move_path "$HOME/Library/LaunchAgents/dev.dragfly.dictare.plist"
        move_path "$HOME/Applications/Dictare.app"
        if command -v brew &>/dev/null && brew list dictare &>/dev/null 2>&1; then
            info "Removing legacy Homebrew formula"
            brew uninstall dictare || true
        fi
        ;;
    Linux)
        systemctl --user stop dictare.service 2>/dev/null || true
        systemctl --user disable dictare.service 2>/dev/null || true
        move_path "$HOME/.config/systemd/user/dictare.service"
        systemctl --user daemon-reload 2>/dev/null || true
        ;;
esac

move_path "$HOME/.local/bin/dictare"
move_path "$HOME/.local/share/dictare/current"
move_path "$HOME/.local/share/dictare/previous"
move_path "$HOME/.local/share/dictare/versions"
move_path "$HOME/.local/share/dictare/locks"
move_path "$HOME/.dictare/python_path"
move_path "$HOME/.dictare/homebrew_bundle_path"

printf "\n"
ok "Uninstall complete."
printf "\n"
printf "  To reinstall with the direct installer:\n"
printf "    ${BOLD}curl -fsSL https://raw.githubusercontent.com/dragfly/dictare/main/install.sh | bash${RESET}\n"
printf "\n"
printf "  Or, when using the Homebrew bootstrap:\n"
printf "    ${BOLD}brew tap dragfly/tap && brew install dictare && dictare setup${RESET}\n"
printf "\n"
