#!/usr/bin/env bash
# Smoke test: verify imports work
set -euo pipefail

echo "=== SMOKE TEST ==="

echo "1. Checking voxtype version..."
python -m voxtype --version

echo "2. Testing PyGObject import..."
python -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk; print('PyGObject OK')"

echo "3. Testing AppIndicator import..."
# Try both variants (Ayatana for Ubuntu/Debian, AppIndicator3 for Fedora/Arch)
python -c "
import gi
try:
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3
    print('AyatanaAppIndicator3 OK')
except:
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3
    print('AppIndicator3 OK')
"

echo "4. Testing TrayApp import..."
python -c "from voxtype.tray.app import TrayApp; print('TrayApp import OK')"

echo "=== SMOKE TEST PASSED ==="
