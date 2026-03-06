#!/usr/bin/env bash
# Uninstall dictare. Auto-detects platform.
# Usage: ./scripts/uninstall.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

case "$(uname -s)" in
    Darwin) exec "${SCRIPT_DIR}/macos/uninstall.sh" "$@" ;;
    Linux)  exec "${SCRIPT_DIR}/linux/uninstall.sh" "$@" ;;
    *)      echo "ERROR: unsupported platform $(uname -s)" >&2; exit 1 ;;
esac
