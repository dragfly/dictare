# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0b8] - 2026-02-13

### Changed

- **Redesigned icons** — circular background (was rounded square), mic centered at 75% fill, gap below base filled. SVG versions added alongside PNGs.
- **Tray hides from Dock** — `_hide_dock_icon()` sets `NSApplicationActivationPolicyAccessory` so only the tray icon shows, no Dock tile.

### Added

- **`scripts/generate_icons.py`** — generates all icon assets (SVG + PNG tray icons, `.icns` app icon).
- **`scripts/brew-rebuild.sh`** — automates sdist build → formula SHA update → `brew reinstall`.
- **Homebrew `post_uninstall` cleanup** — `brew uninstall voxtype` now stops the tray, unloads the LaunchAgent, and removes the `.app` bundle automatically.
- **Homebrew caveats** — `brew info voxtype` shows service/tray start instructions.

## [0.1.0b7] - 2026-02-13

### Fixed

- **Mic indicator shows "Voxtype" instead of "Python"** — the .app bundle launcher script was using `exec` which replaced the bash process with python, causing macOS to attribute mic access to "Python". Now runs python as a child process so the .app bundle identity is preserved.

## [0.1.0b6] - 2026-02-13

### Fixed

- **Service stop now actually stops** — `voxtype service stop` was using `launchctl stop` which only killed the process, but `KeepAlive: true` in the plist caused launchd to restart it immediately. Now uses `launchctl load/unload` to properly register/unregister the agent. Stop means stop.
- **Service status shows loaded state** — `voxtype service status` now distinguishes between "running", "stopped (service not loaded)", and "not installed".
- **Service install no longer double-starts on macOS** — `install()` already calls `launchctl load` (which starts the process); the CLI no longer calls `start()` redundantly after install on macOS.
- **Linux: added `is_loaded()` to systemd backend** — uses `systemctl --user is-active` for consistent status reporting across platforms.

## [0.1.0b5] - 2026-02-13

### Fixed

- **Tray shows stale agent after disconnect** — when the last agent disconnects, the tray UI now correctly clears the target list instead of showing the last connected agent.

## [0.1.0b4] - 2026-02-12

### Added

- **Accessibility permission prompt** — tray app calls `AXIsProcessTrustedWithOptions` at startup to trigger the macOS Accessibility permission dialog automatically, so users don't have to manually find the Python binary in System Settings.

## [0.1.0b3] - 2026-02-12

### Added

- **macOS .app bundle** — `voxtype service install` creates `/Applications/Voxtype.app` so macOS shows "Voxtype" with icon in Accessibility / Input Monitoring settings.
- **Tray icons** — green mic (listening), blue (idle), orange (loading), red (muted) PNG icons for the system tray.
- **App icon** — `.icns` bundle icon with green microphone design.

## [0.1.0b2] - 2026-02-12

### Fixed

- Replace deprecated `typer-slim[standard]` dependency with `typer` (v0.23.0 removed the `standard` extra).
- Fix PyPI classifiers: "Beta" status, remove unsupported Python 3.10/3.12.

### Added

- **Homebrew tap** — `brew install dragfly/voxtype/voxtype`.

## [0.1.0b1] - 2026-02-12

First public beta release.

### Added

- **Voice engine** with Faster Whisper STT, Silero VAD, and configurable TTS (Piper, MLX Audio).
- **OpenVIP protocol** — HTTP API for voice interaction: `/status`, `/control`, `/speech`, SSE agent messaging.
- **Agent multiplexer** (`voxtype agent claude`) — PTY-based session with merged stdin + voice input via SSE.
- **Single-command launch** — agent templates in config: `[agents.claude] command = ["claude"]`.
- **System service** — `voxtype service install/start/stop/status` via launchd (macOS) / systemd (Linux).
- **Status panel** — Rich Live TUI showing model loading progress, STT state, agents, hotkey info.
- **Status bar** — persistent last-row indicator (listening/standby/reconnecting) in agent sessions.
- **Session logging** — JSONL session files in `~/.local/share/voxtype/sessions/` with keystroke tracking.
- **Pipeline architecture** — filters (AgentFilter, InputFilter) and executors (InputExecutor, AgentSwitchExecutor) with PipelineLoader DI.
- **Hotkey support** — tap to toggle listening, double-tap to switch agent (evdev on Linux, pynput on macOS).
- **Multi-agent switching** — voice-activated agent switching with phonetic matching (jellyfish).
- **Hardware auto-detection** — CUDA, MLX (Apple Silicon), CPU fallback with automatic compute type selection.
- **Audio feedback** — configurable sounds for start/stop/transcribing/ready/sent events.
- **Tray app** — system tray icon with status polling and quick controls.
- **OpenVIP SDK integration** — all client-side HTTP uses `openvip.Client` (subscribe, get_status, speak, control).
- **CLI**: `voxtype engine start/stop/status`, `voxtype agent`, `voxtype speak`, `voxtype listen`, `voxtype config`, `voxtype service`, `voxtype dependencies`.
