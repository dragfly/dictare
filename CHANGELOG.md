# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0b38] - 2026-02-14

### Fixed

- **Tray icon delay when resuming from idle** — tray treated the PLAYING state (mic muted during start beep) as "off", so the icon stayed gray until the beep finished + one poll cycle. Now maps "playing" as an active state, matching the status bar behavior. Icon turns green immediately on idle→listening, same as listening→idle.

## [0.1.0b37] - 2026-02-14

### Fixed

- **Status bar shows idle when engine is off** — selected agent now shows "● agent · idle" in gray when engine is in idle state (hotkey toggle). Non-selected agents continue showing "○ agent · standby" in yellow. Previously, the selected agent kept showing "listening" even after the engine was paused.

## [0.1.0b36] - 2026-02-14

### Fixed

- **Agent launch hides command errors** — clear screen was happening after `session.start()`, wiping any immediate error output from the child process (e.g., "command not found"). Now clears before launching so errors are always visible.

## [0.1.0b35] - 2026-02-14

### Changed

- **Rename `derive_message()` → `fork_message()`** — clearer name for the message derivation function in pipeline. Pre-release API cleanup.
- **`PipelineAction(str, Enum)` → `PipelineAction(StrEnum)`** — use Python 3.11 native StrEnum.
- **Fix mypy errors in `PipelineLoader`** — `_build_step` now returns `Filter | Executor | None` instead of `object`.
- **Pin ruff `>=0.14.0,<0.15.0`** — prevents version drift between local and CI.
- **Xvfb for Linux CI** — `xvfb-run` provides virtual X11 display so tray/icon tests run on headless Linux.

## [0.1.0b34] - 2026-02-14

### Changed

- **Pre-release cleanup** — removed dead code (`VoxtypeError` class, unused), extracted shared `_normalize()`/`_tokenize()` from pipeline filters into `pipeline/filters/_text.py`, fixed `pyproject.toml` target-version mismatch (py310 → py311), removed redundant `typer` from dev extras. Added debug logging for partial transcription errors in engine.

### Removed

- Stale debug/build files scrubbed from git history via `git filter-repo`

## [0.1.0b33] - 2026-02-14

### Changed

- **Fast test suite: 452 tests in 1.2s** — marked 23 integration tests (app bundle, http server, race conditions, thread safety) as `@pytest.mark.slow`. Default `pytest` runs only fast logic tests. CI runs all with `pytest -m ''`.
- **Tray: readable Status and About text** — removed `enabled=False` from status line and version text. Items are now full-contrast black instead of greyed out.

## [0.1.0b32] - 2026-02-14

### Fixed

- **Test suite 11.6s → 6.3s** — controller `stop()` now sends a sentinel to wake the worker thread immediately instead of waiting up to 100ms for the `queue.get(timeout=0.1)` to expire. Each of ~30 engine/controller tests was wasting ~100ms on shutdown.

## [0.1.0b31] - 2026-02-14

### Fixed

- **Output mode switch crash** — switching from agents to keyboard via tray crashed with `AttributeError: '_config'`. Typo: `self._config` → `self.config`. Added 5 tests covering mode switching (keyboard→agents, agents→keyboard, noop, preservation of existing agents, invalid mode).

## [0.1.0b30] - 2026-02-14

### Added

- **Tray: Settings menu item** — opens `~/.config/voxtype/config.toml` in the default editor. Uses `open -t` on macOS, `xdg-open` or `$EDITOR` on Linux.
- **Tray: About submenu** — version info moved from main menu into an About submenu.

### Changed

- **Tray: version removed from main menu** — no longer shows raw version string at the bottom of the dropdown.

## [0.1.0b29] - 2026-02-14

### Changed

- **Submit triggers: multi-word only** — removed all single-word triggers (`submit`, `send`, `go`) from defaults. Single words trigger too easily during normal speech. Only multi-word sequences like `["ok", "send"]` remain.
- **Config template: DE/FR examples** — added commented German and French trigger examples alongside English.

## [0.1.0b28] - 2026-02-14

### Changed

- **Submit filter: English-only default** — removed hardcoded Italian/Spanish/German/French triggers from code defaults. Only English triggers ship by default. Users add their language via `[pipeline.submit_filter.triggers]` section in config.
- **Config template: expanded TOML triggers** — triggers shown as multi-line arrays under `[pipeline.submit_filter.triggers]` instead of unreadable single-line JSON.

## [0.1.0b27] - 2026-02-14

### Changed

- **Tray polling 500ms → 100ms** — faster visual feedback on hotkey toggle (icon color change is now near-instant).
- **Config template cleanup** — `create_default_config()` now generates all values commented out. Only non-default values need to be uncommented.

## [0.1.0b26] - 2026-02-14

### Fixed

- **Hotkey toggle bounces back** — tray and engine both registered a hotkey listener on the same key, causing two toggles per tap (OFF→LISTENING→OFF cancelled out as instant bounce). Removed the tray's listener — hotkey is the engine's responsibility.

## [0.1.0b25] - 2026-02-14

### Fixed

- **No audio feedback on brew install** — `.gitignore` pattern `sounds/` was excluding `src/voxtype/audio/sounds/*.mp3` from the sdist tarball. Changed to `/sounds/` to only ignore the root-level originals directory.

## [0.1.0b24] - 2026-02-14

### Fixed

- **Engine crash on brew install** — removed `rm_rf` of PyAV `.dylibs/` from brew formula. The hack prevented the install_name_tool warning but broke `av` at runtime (dlopen failure), causing the engine to crash in a respawn loop.

### Changed

- **`src/voxtype/libs/` — pure Python replacement library** — moved `metaphone()` and `levenshtein_distance()` into `voxtype.libs.jellyfish`, a drop-in module with the same interface as the external `jellyfish` package. To switch back: change `from voxtype.libs.jellyfish import ...` to `from jellyfish import ...`.
- **`uvicorn[standard]` → `uvicorn`** — removed `[standard]` extras which pulled in `watchfiles` (another Rust extension with the same install_name_tool issue). `watchfiles` is only used for `--reload` in development, not needed in production.

### Removed

- **jellyfish dependency** — replaced with pure Python in `voxtype.libs.jellyfish`. The jellyfish Rust extension (`_rustyfish.so`) caused Homebrew's `install_name_tool` to fail with "header too small" during `brew install`.

## [0.1.0b23] - 2026-02-13

### Removed

- **jellyfish dependency** — replaced with pure Python `_metaphone()` and `_levenshtein_distance()` in `agent_filter.py`. The jellyfish Rust extension (`_rustyfish.so`) caused Homebrew's `install_name_tool` to fail with "header too small" during `brew install`. Since these functions are only called on short agent names during occasional voice commands (not a hot path), the pure Python implementation has no meaningful performance impact.

## [0.1.0b20] - 2026-02-13

### Added

- **Microphone permission support** — Swift launcher now requests mic permission (shows "Voxtype" in dialog). `NSMicrophoneUsageDescription` added to Info.plist. Without this, macOS silently feeds zeros to the audio stream.
- **Microphone permission in `/status`** — new `platform.permissions.microphone` field. Tray shows "Grant Microphone Permission" menu item when not granted, clicking opens System Settings → Microphone directly.
- **`voxtype.platform.microphone` module** — `is_microphone_granted()` (cached 5s) and `open_microphone_settings()`.

### Fixed

- **Brew `post_uninstall` cleanup** — now removes Accessibility TCC entry via `tccutil reset`.

## [0.1.0b19] - 2026-02-13

### Added

- **macOS .app bundle via Homebrew** — `brew install` now creates `/Applications/Voxtype.app` so macOS shows "Voxtype" (not "Python") in mic indicator, Accessibility settings, and Activity Monitor.
- **Accessibility permission in `/status`** — new `platform.permissions.accessibility` field reports whether Accessibility is granted. Tray shows "Grant Accessibility Permission" menu item when missing, clicking opens System Settings directly.
- **Shared accessibility utility** — `voxtype.platform.accessibility` module with `is_accessibility_granted()`, `request_accessibility()`, `open_accessibility_settings()`. Cached (5s TTL) for polling efficiency.

### Fixed

- **Brew uninstall cleanup** — `post_uninstall` now stops brew service and kills engine/tray processes (not agent sessions).

## [0.1.0b18] - 2026-02-13

### Fixed

- **`__keyboard__` agent hidden from API and UI** — internal agents (like `__keyboard__`) are no longer visible in `/status`, tray, or status panel. `RESERVED_AGENT_IDS` set + `visible_agents`/`visible_current_agent` properties centralize filtering. HTTP SSE endpoint returns 403 for reserved agent IDs (security hardening).

## [0.1.0b17] - 2026-02-13

### Fixed

- **Tray output mode toggle works** — polling was overwriting the user's keyboard/agents selection every 500ms with the engine's reported mode. Now the tray owns the output mode (from config), polling no longer touches it.

## [0.1.0b16] - 2026-02-13

### Changed

- **Zero-config post-install** — both `brew install` and `curl | bash` produce a ready-to-use install. No extra commands needed: just `voxtype agent claude`. Models auto-download on first engine start, service is managed automatically.
- **`voxtype setup` skips service if Homebrew is active** — detects `brew services` and avoids creating a duplicate plist.
- **Simplified Homebrew caveats** — removed `voxtype setup` instruction; models download automatically.

## [0.1.0b15] - 2026-02-13

### Fixed

- **Daemon respects config output mode** — removed forced `agents` override in daemon mode. If config says `mode = "keyboard"`, the daemon creates a KeyboardAgent and injects keystrokes into the focused window (global dictation). Tray now shows the correct mode.

### Added

- **Tray: Advanced submenu** with "Restart Engine" — restarts the OS service (launchd/systemd) without leaving the tray. Useful after config changes.

## [0.1.0b14] - 2026-02-13

### Fixed

- **`brew-rebuild.sh` works on Linux** — uses `$(brew --prefix)` instead of hardcoded `/opt/homebrew`, handles BSD/GNU `sed` and `shasum`/`sha256sum` differences, derives all paths relative to project dir.

### Changed

- **openvip SDK path** — moved from `nottoplay/openvip-sdks` to `openvip-dev/sdks` across `pyproject.toml`, `uv.lock`, `brew-rebuild.sh`, and `publish.sh`.

### Added

- **`docs/notes/installation-guide.md`** — comprehensive install guide: macOS/Linux channel comparison, service management, cross-platform installer landscape research, reusable pattern for future projects.

## [0.1.0b13] - 2026-02-13

### Added

- **`install.sh`** — `curl | bash` installer (Ollama-style): detects OS, installs uv + voxtype, runs setup wizard. Supports `--skip-setup` and `--uninstall`.
- **`scripts/publish.sh`** — interactive PyPI publish workflow: tests, builds + uploads openvip then voxtype, creates GitHub release. Supports `--dry-run`.

## [0.1.0b12] - 2026-02-13

### Removed

- **Dead CLI commands** — removed `listen`, `execute`, `transcribe`, `devices`, `logs`, `completion`, `init`, `cmd`, `backends` (18 → 9 commands).
- **Engine start flags** — removed `--keyboard/-K`, `--agents/-A`, `--model/-m`, `--language/-l`. Mode comes from config; daemon always uses agents mode.
- **Models subcommands** — removed `use` (use `config set stt.model X`) and `resolve` (auto-pull at engine start).
- **Config subcommands** — removed `path` and `shortcuts`.
- **speak `--no-engine`** — engine is now auto-detected; falls back to in-process TTS automatically.

### Changed

- **`models download` → `pull`**, **`models clear` → `rm`** — aligned with Ollama/Docker conventions.
- **Default hotkey → Right Command** on macOS (`KEY_RIGHTMETA` instead of `KEY_LEFTMETA`).
- **Service plist/unit simplified** — `engine start -d` without `--agents` (daemon always implies agents mode).
- **Tray starts in "disconnected" state** — red icon until engine responds, instead of silent yellow.

### Added

- **`voxtype setup`** — first-time wizard: creates config, downloads models, installs service, prompts Accessibility permission.
- **Auto-pull models at engine start** — missing models are downloaded automatically instead of exiting with an error.

## [0.1.0b11] - 2026-02-13

### Changed

- **Tray icons: colored circle + white mic** — state conveyed by background color (green=listening, yellow=idle, blue=loading, red=disconnected) using approved SVG mic design. Monkey-patched pystray for crisp Retina rendering (NSImage at @2x pixels with point-size declaration).

## [0.1.0b10] - 2026-02-13

### Fixed

- **Tray icon adapts to dark/light menu bar** — pystray ignores `template=True`, so the NSImage was never marked as template. Monkey-patched `_assert_image` to call `setTemplate_(True)`. Icons regenerated at correct 18x18 @1x / 36x36 @2x size per Apple HIG.

## [0.1.0b8] - 2026-02-13

### Fixed

- **Agent starts without engine** — `voxtype agent` no longer blocks with an error if the engine is not running. It starts immediately showing "connecting..." in the status bar and reconnects automatically when the engine becomes available.

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
