# Multi-Distro Install Testing

Tests `linux-install.sh` on different Linux distributions using Docker.

## Usage

```bash
# Test all distros
./scripts/test-distros/run.sh

# Test specific distro
./scripts/test-distros/run.sh ubuntu
./scripts/test-distros/run.sh debian
./scripts/test-distros/run.sh fedora
./scripts/test-distros/run.sh arch
```

## What it tests

1. System packages install correctly (apt/dnf/pacman)
2. uv installs
3. Python venv + PyGObject build
4. dictare installs from source
5. `dictare --version` runs

## Limitations

- No GPU testing (requires nvidia-docker)
- No audio device testing (no hardware)
- No systemd (Docker doesn't run systemd by default)
- No tray icon testing (headless)

These are **smoke tests** for package installation, not full functional tests.
