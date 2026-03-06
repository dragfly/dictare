#!/usr/bin/env bash
# Hard reset Dictare macOS permission/runtime state.
# Use when TCC/runtime state is inconsistent and you want a deterministic restart.
set -euo pipefail

BREW_PREFIX="$(brew --prefix 2>/dev/null || true)"
DICTARE_BIN=""
if [[ -n "${BREW_PREFIX}" && -x "${BREW_PREFIX}/bin/dictare" ]]; then
  DICTARE_BIN="${BREW_PREFIX}/bin/dictare"
elif command -v dictare >/dev/null 2>&1; then
  DICTARE_BIN="$(command -v dictare)"
fi

if [[ -z "${DICTARE_BIN}" ]]; then
  echo "ERROR: dictare binary not found in PATH or brew prefix." >&2
  exit 1
fi

echo "This will:"
echo "  1) stop Dictare service/tray"
echo "  2) clear local runtime status files"
echo "  3) reset macOS TCC permissions for dev.dragfly.dictare"
echo "  4) reinstall/start Dictare service"
echo
read -r -p "Continue? [y/N] " REPLY
if [[ ! "${REPLY}" =~ ^[Yy]$ ]]; then
  echo "Cancelled."
  exit 0
fi

echo "==> Stopping Dictare..."
"${DICTARE_BIN}" tray stop 2>/dev/null || true
"${DICTARE_BIN}" service stop 2>/dev/null || true
pkill -f "Dictare.app/Contents/MacOS/Dictare" 2>/dev/null || true

echo "==> Clearing local status files..."
rm -f "${HOME}/.dictare/hotkey_status" \
      "${HOME}/.dictare/hotkey_runtime_status" \
      "${HOME}/.dictare/accessibility_status" \
      "${HOME}/.dictare/input_monitoring_setup"

echo "==> Resetting TCC permissions..."
tccutil reset Accessibility dev.dragfly.dictare || true
tccutil reset Microphone dev.dragfly.dictare || true
tccutil reset ListenEvent dev.dragfly.dictare || true
# Also reset legacy Bundle ID (pre-v0.1.135)
tccutil reset Accessibility com.dragfly.dictare 2>/dev/null || true
tccutil reset Microphone com.dragfly.dictare 2>/dev/null || true
tccutil reset ListenEvent com.dragfly.dictare 2>/dev/null || true

echo "==> Reinstalling and starting Dictare service..."
"${DICTARE_BIN}" service install
"${DICTARE_BIN}" service start

echo
echo "Done."
echo "Now open Dictare and grant permissions when prompted."
echo "Then open Advanced -> Permissions and run 'Probe Hotkey'."
