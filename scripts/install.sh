#!/usr/bin/env bash
# Install dictare (app only — uses openvip from PyPI).
# Auto-detects platform and runs the appropriate installer.
# Usage: ./scripts/install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

case "$(uname -s)" in
    Darwin) exec "${SCRIPT_DIR}/macos-install.sh" "$@" ;;
    Linux)  exec "${SCRIPT_DIR}/linux-install.sh" "$@" ;;
    *)      echo "ERROR: unsupported platform $(uname -s)" >&2; exit 1 ;;
esac
