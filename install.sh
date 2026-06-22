#!/usr/bin/env bash
# Dictare installer -- cross-platform runtime-store install.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/dragfly/dictare/main/install.sh | bash
#   bash install.sh [--version X] [--previous-version X] [--gpu] [--skip-setup]
#
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
RESET='\033[0m'

info()  { printf "${GREEN}==>${RESET} ${BOLD}%s${RESET}\n" "$*"; }
ok()    { printf "${GREEN}==>${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}==>${RESET} %s\n" "$*"; }
error() { printf "${RED}ERROR:${RESET} %s\n" "$*" >&2; exit 1; }

INSTALL_GPU=false
SKIP_SETUP=false
VERSION=""
PREVIOUS_VERSION=""
FROM_PATH=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --gpu) INSTALL_GPU=true; shift ;;
        --skip-setup) SKIP_SETUP=true; shift ;;
        --version) VERSION="${2:-}"; [[ -n "$VERSION" ]] || error "--version requires a value"; shift 2 ;;
        --previous-version) PREVIOUS_VERSION="${2:-}"; [[ -n "$PREVIOUS_VERSION" ]] || error "--previous-version requires a value"; shift 2 ;;
        --from-path) FROM_PATH="${2:-}"; [[ -n "$FROM_PATH" ]] || error "--from-path requires a value"; shift 2 ;;
        --help|-h)
            cat <<'EOF'
Dictare installer

Usage:
  curl -fsSL https://raw.githubusercontent.com/dragfly/dictare/main/install.sh | bash
  bash install.sh [OPTIONS]

Options:
  --version X           Install a specific Dictare version from PyPI
  --previous-version X  Preload a rollback runtime before activating target
  --from-path P         Install from a local sdist/wheel/path
  --gpu                 Enable CUDA GPU dependencies on Linux
  --skip-setup          Install runtime only; skip first-time setup
  --help                Show this help

Install layout:
  ~/.local/share/dictare/versions/<version>/
  ~/.local/share/dictare/current -> versions/<version>
  ~/.local/bin/dictare           -> stable shim
EOF
            exit 0
            ;;
        *) error "Unknown option: $1. Use --help for usage." ;;
    esac
done

OS="$(uname -s)"
ARCH="$(uname -m)"
ORIGINAL_PATH="$PATH"

if [[ "$EUID" -eq 0 ]]; then
    error "Do not run as root. Run as your normal user."
fi

printf "\n"
info "Installing Dictare ($OS $ARCH)"
printf "\n"

ensure_uv() {
    if command -v uv &>/dev/null; then
        ok "uv found: $(uv --version)"
        return
    fi
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    command -v uv &>/dev/null || error "uv installation failed"
    ok "uv installed"
}

latest_version() {
    python3 - <<'PY'
import json
import urllib.request
with urllib.request.urlopen("https://pypi.org/pypi/dictare/json", timeout=20) as r:
    print(json.load(r)["info"]["version"])
PY
}

version_from_path() {
    python3 - "$1" <<'PY'
import re
import sys
from pathlib import Path

name = Path(sys.argv[1]).name
match = re.search(r"dictare-([0-9][A-Za-z0-9.+!_-]*)\.(?:tar\.gz|whl|zip)$", name)
if not match:
    raise SystemExit(1)
print(match.group(1))
PY
}

source_url() {
    python3 - "$1" <<'PY'
from pathlib import Path
import sys

source = sys.argv[1]
if "://" in source:
    print(source)
else:
    print(Path(source).expanduser().resolve().as_uri())
PY
}

check_linux_prereqs() {
    local missing=()
    local install_cmd=""

    if command -v dpkg &>/dev/null; then
        local appindicator_pkg="gir1.2-appindicator3-0.1"
        if command -v lsb_release &>/dev/null; then
            local distro rel
            distro="$(lsb_release -is 2>/dev/null || true)"
            rel="$(lsb_release -rs 2>/dev/null || echo 0)"
            if [[ "$distro" == "Ubuntu" && "${rel%%.*}" -ge 22 ]]; then
                appindicator_pkg="gir1.2-ayatanaappindicator3-0.1"
            fi
        fi
        local packages=(libportaudio2 portaudio19-dev espeak-ng ydotool "$appindicator_pkg" libgirepository-2.0-dev libcairo2-dev build-essential pkg-config)
        for pkg in "${packages[@]}"; do
            dpkg -l "$pkg" 2>/dev/null | grep -q '^ii' || missing+=("$pkg")
        done
        [[ ${#missing[@]} -eq 0 ]] || install_cmd="sudo apt-get update && sudo apt-get install -y ${missing[*]}"
    elif command -v rpm &>/dev/null; then
        local packages=(portaudio portaudio-devel espeak-ng ydotool libappindicator-gtk3 gobject-introspection-devel cairo-devel gcc pkg-config)
        for pkg in "${packages[@]}"; do
            rpm -q "$pkg" &>/dev/null || missing+=("$pkg")
        done
        [[ ${#missing[@]} -eq 0 ]] || install_cmd="sudo dnf install -y ${missing[*]}"
    elif command -v pacman &>/dev/null; then
        local packages=(portaudio espeak-ng ydotool libappindicator-gtk3 gobject-introspection cairo base-devel pkg-config)
        for pkg in "${packages[@]}"; do
            pacman -Q "$pkg" &>/dev/null || missing+=("$pkg")
        done
        [[ ${#missing[@]} -eq 0 ]] || install_cmd="sudo pacman -S --noconfirm ${missing[*]}"
    fi

    if [[ -n "$install_cmd" ]]; then
        warn "Missing Linux system packages. Run this, then rerun the installer:"
        printf "\n  ${BOLD}%s${RESET}\n\n" "$install_cmd"
        exit 1
    fi

    if ! groups | grep -qw input; then
        warn "Your user is not in the input group. Global hotkey may not work until you run:"
        printf "\n  ${BOLD}sudo usermod -aG input \$USER${RESET}\n"
        printf "  Then log out and back in.\n\n"
    fi
}

check_macos_prereqs() {
    if command -v brew &>/dev/null; then
        if ! brew list portaudio &>/dev/null; then
            info "Installing macOS audio dependency: portaudio"
            brew install portaudio
        fi
    else
        warn "Homebrew is not required for Dictare, but portaudio must be installed on macOS."
        warn "If audio capture fails, install portaudio with your preferred system package manager."
    fi
}

install_macos_launcher() {
    [[ "$OS" == "Darwin" ]] || return

    local app_dest="$HOME/Applications/Dictare.app"
    local tmp_dir
    tmp_dir="$(mktemp -d)"
    local zip="$tmp_dir/Dictare-launcher-universal.zip"
    local extract="$tmp_dir/extract"

    info "Installing signed Dictare launcher..."
    curl -fL \
        "https://github.com/dragfly/dictare/releases/download/launcher/Dictare-launcher-universal.zip" \
        -o "$zip"
    mkdir -p "$extract" "$HOME/Applications"
    ditto -x -k "$zip" "$extract"

    local app_src=""
    if [[ -d "$extract/Dictare.app" ]]; then
        app_src="$extract/Dictare.app"
    elif [[ -d "$extract/Contents" ]]; then
        mkdir -p "$extract/Dictare.app"
        mv "$extract/Contents" "$extract/Dictare.app/Contents"
        app_src="$extract/Dictare.app"
    else
        error "Launcher archive did not contain Dictare.app"
    fi

    if [[ -d "$app_dest" ]]; then
        python3 - "$app_dest" <<'PY'
import shutil
import sys
import time
from pathlib import Path

src = Path(sys.argv[1])
trash = Path.home() / ".dictare" / "trash"
trash.mkdir(parents=True, exist_ok=True)
dst = trash / f"Dictare.app.{int(time.time())}"
counter = 0
while dst.exists():
    counter += 1
    dst = trash / f"Dictare.app.{int(time.time())}.{counter}"
shutil.move(str(src), str(dst))
PY
    fi

    ditto "$app_src" "$app_dest"
    xattr -dr com.apple.quarantine "$app_dest" 2>/dev/null || true
    ok "Launcher installed: $app_dest"
}

install_runtime() {
    local version="$1"
    local root="$HOME/.local/share/dictare"
    local runtime="$root/versions/$version"
    local current="$root/current"
    local previous="$root/previous"
    local tmp_link="$root/.current.tmp.$$"
    local extras=""

    mkdir -p "$root/versions" "$root/locks" "$HOME/.local/bin"

    if [[ "$OS" == "Darwin" && "$ARCH" == "arm64" ]]; then
        extras="mlx"
    elif [[ "$OS" == "Linux" ]]; then
        extras="tray"
        [[ "$INSTALL_GPU" == true ]] && extras="tray,gpu"
    fi

    local spec=""
    if [[ -n "$FROM_PATH" ]]; then
        spec="dictare"
        [[ -n "$extras" ]] && spec="${spec}[${extras}]"
        spec="${spec} @ $(source_url "$FROM_PATH")"
    else
        spec="dictare"
        [[ -n "$extras" ]] && spec="${spec}[${extras}]"
        spec="${spec}==${version}"
    fi

    if [[ ! -x "$runtime/bin/python" ]]; then
        info "Creating runtime: $runtime"
        uv venv --python 3.11 "$runtime"
    fi

    info "Installing $spec"
    local install_cmd=(uv pip install --python "$runtime/bin/python" --prerelease=allow)
    install_cmd+=("$spec")
    "${install_cmd[@]}"

    info "Smoke testing runtime"
    "$runtime/bin/dictare" --version | grep -q "$version" || error "Installed runtime did not report version $version"

    python3 - "$current" "$previous" "$tmp_link" "$runtime" <<'PY'
import os
import sys
from pathlib import Path

current = Path(sys.argv[1])
previous = Path(sys.argv[2])
tmp = Path(sys.argv[3])
runtime = Path(sys.argv[4])

old = current.resolve() if current.exists() else None
if old and old != runtime:
    prev_tmp = previous.with_name(f".{previous.name}.tmp.{os.getpid()}")
    if prev_tmp.exists() or prev_tmp.is_symlink():
        prev_tmp.unlink()
    prev_tmp.symlink_to(old, target_is_directory=True)
    os.replace(prev_tmp, previous)

if tmp.exists() or tmp.is_symlink():
    tmp.unlink()
tmp.symlink_to(runtime, target_is_directory=True)
os.replace(tmp, current)
PY

    cat > "$HOME/.local/bin/dictare" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec "$HOME/.local/share/dictare/current/bin/dictare" "$@"
EOF
    chmod +x "$HOME/.local/bin/dictare"
}

case "$OS" in
    Darwin) check_macos_prereqs ;;
    Linux) check_linux_prereqs ;;
    *) error "Unsupported OS: $OS" ;;
esac

ensure_uv

if [[ -z "$VERSION" && -n "$FROM_PATH" ]]; then
    VERSION="$(version_from_path "$FROM_PATH")" || error "Could not infer version from --from-path. Pass --version."
fi

if [[ -z "$VERSION" ]]; then
    info "Resolving latest Dictare version..."
    VERSION="$(latest_version)"
fi
ok "Target version: $VERSION"

if [[ -n "$PREVIOUS_VERSION" ]]; then
    [[ "$PREVIOUS_VERSION" != "$VERSION" ]] || error "--previous-version must differ from --version"
    info "Preparing rollback runtime: $PREVIOUS_VERSION"
    target_from_path="$FROM_PATH"
    FROM_PATH=""
    install_runtime "$PREVIOUS_VERSION"
    FROM_PATH="$target_from_path"
fi

install_runtime "$VERSION"
install_macos_launcher

export PATH="$HOME/.local/bin:$PATH"

if [[ "$SKIP_SETUP" == false ]]; then
    info "Running first-time setup..."
    "$HOME/.local/bin/dictare" setup
fi

info "Repairing runtime integration..."
"$HOME/.local/bin/dictare" repair

printf "\n"
ok "Dictare installed."
printf "  ${BOLD}dictare agent my-first-session${RESET}\n"
printf "\n"
if [[ ":$ORIGINAL_PATH:" != *":$HOME/.local/bin:"* ]]; then
    warn "~/.local/bin is not in your PATH. Add this to your shell profile:"
    printf "\n  ${BOLD}export PATH=\"\$HOME/.local/bin:\$PATH\"${RESET}\n\n"
fi
