# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.72] - 2026-02-28

### Changed
- Dashboard Engine card: STT, TTS, Hotkey rows now appear first, State and
  Uptime below — aligns the three status indicators with the Permissions column.

## [0.1.71] - 2026-02-28

### Fixed
- Auto-reset TCC `ListenEvent` entries on launcher binary change during
  `dictare service install`: prevents accumulated stale TCC entries from
  blocking the CGEventTap after reinstalls or Homebrew upgrades.

## [0.1.70] - 2026-02-28

### Fixed
- Keyboard-mode injection success reporting is now real, not queue-level:
  `KeyboardAgent.send()` waits for worker completion and returns the actual
  injector result (`type_text` / `send_submit` / `send_newline`), eliminating
  false-positive `"success": true` injection logs when typing did not occur.

## [0.1.69] - 2026-02-28

### Fixed
- Accessibility permission false negatives in macOS doctor/status flow:
  launcher `--check-permissions` now remains authoritative and is no longer
  downgraded by stale runtime `~/.dictare/accessibility_status` values.

## [0.1.68] - 2026-02-28

### Added
- New hard-reset script for macOS permissions/runtime state:
  - `scripts/macos-reset-permissions.sh`
  - stops service/tray, clears local runtime markers, resets TCC grants, and
    reinstalls/restarts Dictare service.

### Fixed
- Accessibility permission status now prefers a runtime signal from the active
  launcher process (`~/.dictare/accessibility_status`) to reduce false
  negatives caused by subprocess identity mismatches.

## [0.1.67] - 2026-02-28

### Fixed
- Permission Doctor probe endpoint no longer blocks the HTTP event loop.
  `POST /permissions/doctor/probe` now runs in a worker thread, preventing
  transient "engine disconnected/restarting" UI errors while probing.
- Permission Doctor diagnosis now prioritizes the hotkey path signal
  (`input_monitoring` + runtime delivery) over Accessibility as a primary
  hotkey failure cause.

### Changed
- Permissions Doctor UI copy now includes a short guided intro and
  auto-refreshes every second while the page is open.
- Added explicit `Restart Dictare` action inside the doctor flow and
  improved per-permission status layout for readability.

## [0.1.66] - 2026-02-28

### Added
- Permission Doctor now returns a deterministic diagnosis payload:
  - `code`
  - `summary`
  - `steps`
  - `recommended_target`
- New tests for diagnosis behavior:
  - `tests/test_permission_doctor.py`

### Changed
- Permission Doctor UI is now guided, not just status-only:
  - diagnosis banner with actionable explanation
  - recommended one-click settings action
  - probe result card with follow-up steps on failure

### Fixed
- Clarified the critical macOS edge case where permissions are granted but
  hotkey events are still not delivered: the doctor now explicitly surfaces
  this state (`granted_but_no_delivery`) and provides a deterministic recovery
  sequence for the user.

## [0.1.65] - 2026-02-28

### Changed
- macOS daemon hotkey path is now IPC-first end-to-end (launcher -> engine),
  with runtime health persisted in `~/.dictare/hotkey_runtime_status`.
- Input Monitoring permission and runtime capture health are now treated as
  separate signals: permission comes from launcher status, runtime health comes
  from delivered tap events.

### Added
- `src/dictare/hotkey/runtime_status.py` for runtime hotkey status persistence
  (`~/.dictare/hotkey_runtime_status`).
- `src/dictare/platform/permission_doctor.py` as single source of truth for
  permission diagnosis and guided runtime probing.
- New HTTP endpoints:
  - `GET /permissions/doctor`
  - `POST /permissions/doctor/open`
  - `POST /permissions/doctor/probe`
- `/hotkey/status` now returns runtime-derived fields when available
  (`active_provider`, `capture_healthy`).
- Settings UI now exposes a single Permission Doctor entrypoint in
  `Advanced -> Permissions`.
- Dashboard now links failed permission/hotkey states directly to the
  Permission Doctor.

### Fixed
- Input Monitoring permission UI no longer reports false negatives when the
  launcher reports `active` but runtime confirmation has not happened yet.

## [0.1.64] - 2026-02-28

### Fixed
- macOS hotkey delivery is now IPC-first: the Swift launcher sends tap events
  to the engine over a local Unix socket with per-event ACK, and falls back to
  `SIGUSR1` if IPC delivery fails.
- Swift launcher `CGEventTap` callback no longer retains events (`passUnretained`
  instead of `passRetained`), preventing ownership leaks in the hotkey path.
- Hotkey health semantics are stricter: only `hotkey_status = "confirmed"` is
  considered healthy (`active` no longer counts as bound/healthy).

### Added
- New hotkey IPC server module (`src/dictare/hotkey/ipc.py`) and integration in
  `dictare serve` (`DICTARE_HOTKEY_TRANSPORT=auto|ipc|signal`).
- Tests for the IPC hotkey transport and ACK behavior.
- Technical postmortem/design document: `codex-hotkey-fix.md`.

## [0.1.63] - 2026-02-28

### Fixed
- App bundle Info.plist was missing `NSInputMonitoringUsageDescription` — on
  Sequoia, without this key macOS can register the TCC permission but silently
  refuse to deliver CGEventTap events, causing `hotkey_status` to stay stuck at
  "active" (never "confirmed") even with Input Monitoring granted.
- Swift launcher: call `CGRequestListenEventAccess()` before every
  `CGEvent.tapCreate()` call to prime TCC authorization in the current process
  context (no-op if permission already granted).

## [0.1.62] - 2026-02-28

### Added
- Settings → Keyboard: hotkey status indicator (confirmed/active/failed) with
  "Fix Input Monitoring" button that opens System Settings → Input Monitoring.
  Useful when CGEventTap is silently broken on Sequoia.
- `GET /hotkey/status` and `POST /hotkey/fix` HTTP endpoints.

## [0.1.61] - 2026-02-28

### Fixed
- Swift launcher: when macOS disables the CGEventTap (`tapDisabledByTimeout` /
  `tapDisabledByUserInput`), recreate the tap from scratch instead of calling
  `CGEvent.tapEnable`. On Sequoia, re-enabling an existing tap after a system
  disable leaves it silently delivering no events; destroying and recreating it
  reliably restores hotkey functionality.

## [0.1.60] - 2026-02-28

### Fixed
- Tray always showed "Disconnected" when launched via launchd: `lifecycle.py`
  `start_tray(foreground=True)` was creating a bare `TrayApp().run()` with no
  poll thread — it now delegates to `app.main()` which does the full setup
  (status polling, callbacks, logging).

### Added
- `dictare logs --tray`: shows tray stdout/stderr logs instead of engine logs.

## [0.1.59] - 2026-02-28

### Fixed
- `install_tray()`: unload plist before recreating to prevent `launchctl load`
  failing with Error 5 when the service is already registered.
- `install()`: always reinstall tray plist (not only when missing) so the
  python_path stays in sync after `brew upgrade dictare`.

## [0.1.58] - 2026-02-28

### Added
- `service install` now also installs and starts the tray LaunchAgent on macOS
  (idempotent — safe to run multiple times).
- Homebrew formula: `post_install` hook runs `dictare service install`
  automatically after `brew install`, so new users get engine + tray running
  without any terminal interaction.
- Settings → Advanced → Daemon: "Launch at login" toggle — enables or disables
  auto-start of engine and tray at login (macOS only, hidden on Linux).
- `GET /system` and `POST /system` HTTP endpoints for reading and writing
  system-level settings (currently: `launch_at_login`).
- `launchd.py`: `launch_at_login_enabled()`, `enable_launch_at_login()`,
  `disable_launch_at_login()` helpers controlling both engine and tray plists.

### Changed
- `macos-install.sh`: removed the "Use 'dictare tray start'" hint since the
  tray is now started automatically by `service install`.

## [0.1.57] - 2026-02-28

### Changed
- Launcher: `Dictare.app` now calls `launchctl start com.dragfly.dictare.tray`
  on startup — ensures the tray is running even if launchd did not auto-start
  it (idempotent: no-op if already running).
- Daemon: `install_tray()` uses the stable Homebrew symlink
  (`/opt/homebrew/opt/dictare/…`) instead of the versioned `sys.executable`
  path, so the tray LaunchAgent survives `brew upgrade dictare` without
  needing to re-run `dictare service install`.

## [0.1.56] - 2026-02-27

### Changed
- Dashboard: removed "agents mode" badge from Engine card header (redundant
  with Keyboard/Agents toggle buttons already in the card).
- Dashboard: TTS and Hotkey rows no longer show "active" label when healthy;
  only display an error indicator when unavailable or misconfigured.
- Dashboard: Permissions items stacked vertically; grid adjusted to
  `3fr 2fr` giving Engine card more horizontal space.
- Dashboard: agent pills are now clickable — click switches the active agent
  via `output.set_agent`.
- Dashboard: "active" label removed from agent pills (fill colour is
  sufficient to indicate the selected agent).
- Settings nav: selected theme icon now has a visible ring border to
  distinguish it from the other two.

## [0.1.55] - 2026-02-27

### Added
- Models page: unified trash button to remove downloaded files (HuggingFace
  model cache and/or isolated venv). Shown for any non-builtin, non-selected
  capability that has something installed (`venv_installed || model_cached`).
  `DELETE /capabilities/{id}/install` now cleans up both venv and HF cache.

## [0.1.54] - 2026-02-27

### Added
- UI: light/dark/system theme toggle in the sidebar, persisted to
  `localStorage`. Default is "system" (follows OS preference). No flash on
  load (inline script in `<head>` applies the class before first paint).
- UI: wordmark updated to match dictare.io — "DICTA" bold + "re" in purple
  (#6d5ce6).

## [0.1.53] - 2026-02-27

### Fixed
- Engine crash on hotkey press during startup: SIGUSR1 signal handler was
  installed *after* `controller.start()` (model loading ~20 s). An unhandled
  SIGUSR1 during that window terminated the process (default UNIX behaviour).
  All signal handlers (SIGTERM, SIGINT, SIGUSR1) are now installed before
  `controller.start()`.

## [0.1.52] - 2026-02-27

### Changed
- Tray: replaced SSE-based status streaming with simple HTTP polling every 1 s
  (`client.get_status()`). Eliminates all stuck-state bugs (e.g. stuck
  "Restarting…" after engine restart) caused by SSE reconnection edge cases.
- Tray: removed `_restarting` state/flag entirely. Valid states are now:
  `disconnected`, `loading`, `off`, `listening`.
- Tray: disconnected icon renamed from `dictare_muted` to `dictare_disconnected`
  for clarity; new icon asset added.

## [0.1.51] - 2026-02-27

### Fixed
- Dashboard: `accessibility_url` and `microphone_url` keys no longer appear
  as fake permission toggles — filtered client-side.
- Dashboard: Hotkey row shows "confirmed" (green), "confirming…" (yellow), or
  "no permission" (red) based on `hotkey.status` from the engine.
- Engine: `hotkey.bound` now reads `~/.dictare/hotkey_status` written by the
  Swift launcher instead of always returning `False` in daemon mode.
  New `hotkey.status` field in `/status` for fine-grained diagnostics.

## [0.1.50] - 2026-02-27

### Fixed
- MLX Whisper: corrected HuggingFace repo IDs for tiny/base/small/medium —
  use `-mlx` suffix repos (`whisper-tiny-mlx` etc.) which are the native MLX
  format. The bare names were removed or are transformers-only.

## [0.1.49] - 2026-02-27

### Fixed
- MLX Whisper: fallback repo pattern also uses `-mlx` suffix.

## [0.1.48] - 2026-02-27

### Fixed
- Permissions: `input_monitoring` was reported as `false` (tray icon red) even
  when the hotkey was fully working. `_check_input_monitoring()` now accepts
  both `"active"` and `"confirmed"` hotkey_status values.
- Permissions: `accessibility` was hardcoded to `true` — keyboard mode showed
  green even without the Accessibility grant. Now read from the launcher's
  `--check-permissions` output.

## [0.1.47] - 2026-02-27

### Fixed
- Install: `service install` no longer blocks for 30 s when the Input
  Monitoring permission dialog doesn't appear. Removed `--wait-apps` from
  the `open` call — the dialog appears in the background without holding up
  the install sequence.

## [0.1.46] - 2026-02-27

### Added
- Swift launcher: log `Right Cmd DOWN/UP`, tap accepted/rejected, and
  `SIGUSR1 sent to PID` to stderr for hotkey diagnostics.
  (`tail -f ~/Library/Logs/dictare/stderr.log`)
- Swift launcher: CGEventTap now writes `hotkey_status = "confirmed"` only
  after the first real event is received. On Sequoia, `CGEvent.tapCreate()`
  can succeed while the tap silently delivers nothing; "confirmed" is the only
  reliable signal.

## [0.1.45] - 2026-02-27

### Changed
- Swift launcher: log engine exit code and termination reason when the Python
  child exits unexpectedly (`Engine exited: status=X reason=Y` in stderr).
  Helps diagnose silent restarts during install (status=9/reason=2 = SIGKILL,
  status=0/reason=1 = clean exit).

## [0.1.44] - 2026-02-27

### Changed
- Models page: replaced vertical cards with two compact tables (STT / TTS),
  columns: Name · Description · Size · Status · Actions.
- Engine status bar: health poll interval 2s → 1s, timeout 2s → 1s
  (health endpoint is synchronous, responds in <1 ms).

## [0.1.43] - 2026-02-27

### Fixed
- CSS 404 on Linux: `.gitignore` had `assets/` (unanchored) which matched
  `src/dictare/ui/dist/_app/immutable/assets/`, causing CSS chunks to be
  untracked and missing after `git pull`. Changed to `/assets/` (root-only).
  Added the previously-excluded `0.ZEYxg2Jv.css` to the repository.

## [0.1.42] - 2026-02-27

### Fixed
- Linux: `systemctl stop` hung for 90s (systemd default) when the process
  didn't respond to SIGTERM. Added `TimeoutStopSec=10` and `KillMode=control-group`
  to the unit file so the engine is force-killed after 10s.
- Linux install script: `stop` step now falls back to `systemctl kill` if the
  stop command times out, preventing the install from blocking.

## [0.1.41] - 2026-02-27

### Changed
- Dashboard: Engine (left) | Permissions (right), Agents full-width below.

## [0.1.40] - 2026-02-27

### Changed
- Rebuilt UI dist with purple squircle icon in settings nav header.

## [0.1.39] - 2026-02-27

### Changed
- Settings UI nav: added purple squircle icon next to "Dictare" label (top-left).

## [0.1.38] - 2026-02-27

### Changed
- Replaced all tray icons with new official Dictare brand icons (purple mic).
- State→icon mapping: idle=gray, active=purple, loading=yellow, disconnected=red.
- Updated `Dictare.icns` with new purple squircle app icon.
- `restarting` state now shows yellow (loading) icon instead of gray.
- Added `assets/` to `.gitignore`.

## [0.1.37] - 2026-02-27

### Changed
- `speak_text()` checks `_tts_error` before `_tts_engine is None` for clearer
  error messages when TTS failed to load.
- Replaced f-string logging with `%s` placeholders in `http_server.py`,
  `engine.py`, `controller.py` (5 call sites).

## [0.1.36] - 2026-02-27

### Changed
- Tightened bare `except Exception` to specific types: `ValueError` for JSON
  parse, `subprocess.TimeoutExpired` for worker stop, `OSError` for file I/O,
  `json.JSONDecodeError` for config parsing.
- Extracted magic numbers to named constants: `_PLAYBACK_DEADLINE_S`,
  `_TTS_WORKER_CONNECT_TIMEOUT`, `_QUEUE_POLL_S`, `_JOB_CLEANUP_DELAY`, etc.
- Audio device query failures now log `debug` instead of silently returning None.
- `metaphone()` docstring documents CC=62 as intentional (avoids jellyfish dep).

### Added
- 13 regression tests covering exception type tightening, magic number constants,
  audio capture logging, and metaphone documentation.

## [0.1.35] - 2026-02-27

### Changed
- `request_id` → `message_id` throughout TTS flow (proxy, worker, manager, server,
  tests) to align with OpenVIP spec `id` field naming.
- Removed auto-restart on model selection — `POST /capabilities/{cap_id}/select`
  now returns `restart_required: true` and lets the user decide when to restart.
- Replaced nested `getattr` chain for TTS completion with public `complete_tts()`
  methods on Engine → TTSManager → WorkerTTSEngine.
- Event queue in `StateController` is now unlimited (was `maxsize=100`) — events
  are small and consumed fast; dropping them silently was a worse failure mode.

## [0.1.34] - 2026-02-27

### Added
- Tray menu: Start/Stop Service under Advanced, using `is_loaded()` from the
  native service backend (launchd/systemd) to show the correct action. Menu
  updates automatically after each start/stop.

### Changed
- Tray menu: `isinstance` type narrowing for SSE message dispatch instead of
  `getattr` hack.

## [0.1.33] - 2026-02-27

### Fixed
- Newline regression: transcriptions no longer went to new lines between
  sentences. Root cause: SDK regeneration produced Pydantic v2 models that
  silently dropped `x_input` extension fields. Fixed via openvip SDK rc7
  (`extra="allow"` + `from_dict` pass-through).
- `dictare speak stop` / `--timeout` now uses openvip SDK (`Client.stop_speech()`)
  instead of raw urllib calls.

### Added
- `scripts/full-install.sh`: dev install script that regenerates SDK from local
  spec, builds SDK sdist, and installs dictare with the local SDK.
- `scripts/install.sh`: app-only install, auto-detects platform.
- `scripts/macos-install.sh`: when `OPENVIP_SDK_DIST` is set (by full-install.sh),
  injects `--find-links` into the Homebrew formula so `uv tool install` uses the
  local SDK instead of PyPI.
- 11 regression tests (`test_sdk_extension_fields.py`) verifying extension fields
  survive the full SDK deserialization path (JSON → `from_dict()` → `to_dict()` →
  `InputExecutor`).

## [0.1.32] - 2026-02-26

### Fixed
- `dictare speak -t N`: on timeout, audio is now stopped automatically and the
  error message reads "Timed out after Ns — audio stopped." instead of the
  misleading "Engine not running." A timeout means the engine is running but
  playback exceeded the limit; a refused connection means the engine is down.

## [0.1.31] - 2026-02-26

### Added
- `dictare speak stop` — interrupts the currently playing TTS audio immediately.
  Sends SIGUSR2 to the TTS worker subprocess (kokoro/piper/etc.), which kills
  the audio player (`afplay`/`paplay`/`aplay`) mid-playback. Works for
  in-process engines (say/espeak) too via `stop_audio_native()`.
- `dictare speak --timeout` (`-t`) — configurable request timeout (default 300s,
  was previously hard-coded to 30s). Avoids "Engine not running" errors when
  piping long texts.

## [0.1.30] - 2026-02-26

### Fixed
- TTS worker crash on startup: `secrets.token_urlsafe()` can produce tokens
  starting with `-`, which argparse interprets as a flag instead of a value.
  Switched to `token_hex(32)` (hex-only, never starts with `-`).

## [0.1.29] - 2026-02-26

### Fixed
- `dictare speak -v if_sara -l fr` now respects the explicit `-l` override.
  Priority: explicit `-l` > voice prefix > worker default language.
  The CLI no longer passes `language="en"` by default (would silently override
  voice-inferred language); the worker already knows its configured language.

## [0.1.28] - 2026-02-26

### Fixed
- Kokoro TTS: Italian (and other non-English) voices now use correct phonetics.
  Previously `dictare speak "ciao" -v if_sara` would pronounce with English
  phonetics because `language="en"` from config overrode the voice's language.
  Voice prefix now determines phonetics: `if_`/`im_` → Italian, `af_`/`am_` →
  American English, `bf_`/`bm_` → British English, etc.

## [0.1.27] - 2026-02-26

### Fixed
- `POST /speech` response now includes `openvip: "1.0"` field, satisfying
  the `SpeechResponse` model validation in the openvip SDK client.

## [0.1.26] - 2026-02-26

### Fixed
- TTS worker no longer crashes on `SpeechRequest` messages: removed use of
  `additional_properties` (old SDK pattern) in favour of native model fields.
  `proxy.py` now uses the OpenVIP message `id` as the completion tracking key
  (instead of an out-of-band `request_id` extension field). `voice` is now a
  first-class field in the OpenVIP spec and SDK (openvip>=1.0.0rc4).

## [0.1.25] - 2026-02-26

### Fixed
- `dictare speak` (and `llm "..." | dictare speak`) now works correctly — the
  openvip SDK `create_speech_request()` was not generating `id` and `timestamp`
  fields, causing HTTP 422 "Not OpenVIP v1.0 compliant" errors. Fixed by
  regenerating the SDK from the spec (`SpeechRequest` inherits from `Message`
  which requires both fields) and updating `create_speech_request()` to
  auto-fill them. Requires openvip>=1.0.0rc3.

## [0.1.24] - 2026-02-26

### Fixed
- Tray icon stays red ("Status: Disconnected") on fresh install even after engine starts:
  the SSE `on_disconnect` callback now only switches the tray to red if it has previously
  had a successful connection (`_connected_once` flag). On first startup, connection
  failures are silent retries — the tray only updates once the engine is reachable.

## [0.1.23] - 2026-02-26

### Changed
- `openvip` dependency now resolved from PyPI (`>=1.0.0rc1`) — no more local tarball
- Removed `[tool.uv.sources]` local path override for openvip
- `macos-install.sh`: removed openvip build step and `--find-links` flag
- Homebrew formula: removed `openvip_tarball` and `--find-links` (openvip on PyPI)

## [0.1.22] - 2026-02-26

### Fixed
- App bundle icon: rename `Voxtype.icns` → `Dictare.icns` so TCC (Input Monitoring,
  Privacy) shows the correct icon instead of a blank square
- `service install` permission message: remove incorrect "Click + → select" instruction;
  macOS shows the permission dialog automatically when the launcher runs
- `macos-install.sh` service start: `grep "not installed"` instead of `"installed"` to
  correctly detect uninstalled state (prevented auto-start after fresh install)

## [0.1.21] - 2026-02-26

### Added
- Test coverage for session helpers: `KeystrokeCounter`, session log path
  format, `_write_session_start`/`_write_session_end`, `_log_event` error
  handling, and `_write_all` short-write loop (29 new tests)
- Test coverage for stats persistence: `load_stats`/`save_stats` round-trip,
  `update_keystrokes`, `update_stats`, `get_model_load_time`,
  `save_model_load_time` warm-load guard (17 new tests)

## [0.1.20] - 2026-02-26

### Added
- Test coverage for status bar: `_format_cwd`, right-side label construction,
  `_write_to_pty` error handling, agent label computation (17 new tests)

## [0.1.19] - 2026-02-26

### Added
- OpenVIP v1.0 message validation on `/agents/{id}/messages` and `/speech`
  endpoints — non-compliant payloads are rejected with 422 and a clear
  "Not OpenVIP v1.0 compliant" error message

## [0.1.18] - 2026-02-26

### Added
- Current directory shown in status bar right side — `~/repos/proj · [opus] · dictare 0.1.18`;
  home prefix replaced with `~`, long paths truncated from the left with `…`

### Changed
- Alignment with OpenVIP v1.0 spec

## [0.1.17] - 2026-02-26

### Added
- Agent type or command shown in status bar right side — `[opus] · dictare 0.1.17`
  when launched with a type, or first 30 chars of the command when using `--`

## [0.1.16] - 2026-02-26

### Fixed
- Hotkey capture in settings now works on macOS — clicking Capture and pressing
  a key correctly updates the hotkey instead of reverting immediately

## [0.1.15] - 2026-02-26

### Fixed
- Launching the same agent session twice now exits immediately with an error
  instead of opening a broken terminal that receives no voice input

## [0.1.14] - 2026-02-25

### Fixed
- TTS not working on Linux after a fresh install

## [0.1.13] - 2026-02-25

### Fixed
- TTS engine failing to start after a fresh install

## [0.1.12] - 2026-02-25

### Fixed
- TTS engine failing to start in development environments

## [0.1.11] - 2026-02-25

### Fixed
- TTS errors now logged correctly; configuration templates always complete

## [0.1.10] - 2026-02-25

### Fixed
- Settings editor no longer misreads multi-line configuration values

## [0.1.9] - 2026-02-25

### Added
- Submit trigger words now work regardless of the detected spoken language

## [0.1.8] - 2026-02-25

### Changed
- Internal refactoring: TTS management extracted into dedicated module

## [0.1.7] - 2026-02-25

### Changed
- Internal refactoring: agent management extracted into dedicated module

## [0.1.6] - 2026-02-25

### Fixed
- TTS audio output on macOS further stabilised

## [0.1.5] - 2026-02-25

### Fixed
- Improved stability when restarting the engine from the dashboard

## [0.1.4] - 2026-02-25

### Fixed
- Extended correct audio output to the macOS built-in speech engine

## [0.1.3] - 2026-02-25

### Fixed
- Settings editor handles all configuration formats correctly

## [0.1.2] - 2026-02-25

### Fixed
- Dashboard correctly detects when the engine has finished restarting

## [0.1.1] - 2026-02-25

### Fixed
- Hotkey no longer stops working silently after an app update on macOS

## [0.1.0] - 2026-02-25

### Added

**Core**
- **Voice-to-Agent pipeline** — speech is captured, transcribed, filtered, and
  delivered to a connected AI coding agent (Claude Code, Cursor, Aider, or any
  CLI tool)
- **Engine as system service** — runs at login via launchd (macOS) / systemd
  (Linux), preloads STT models for zero cold-start latency. Same model as Ollama.
- **Single-command agent launch** — `dictare agent claude` starts an agent
  session; speak and the agent receives your words

**Speech Recognition (STT)**
- **Whisper (faster-whisper)** — CTranslate2 runtime, Intel/AMD/Linux
- **Whisper (MLX)** — Apple Silicon native, hardware-accelerated
- **Parakeet v3** — ONNX runtime (~15 MB), 25 European languages, auto language
  detection; no PyTorch required
- Automatic engine selection based on hardware

**Text-to-Speech (TTS)**
- **macOS `say`** — zero-install on macOS
- **espeak-ng** — zero-install on Linux
- **Piper** — neural TTS
- **Kokoro** — lightweight ONNX neural TTS

**Pipeline**
- **Submit filter** — detects trigger words ("send", "ok", "submit", …) and
  sends Enter to the agent; multilingual
- **Agent filter** — voice-switches between agents
- **Configurable pipeline** — filters and executors defined in configuration

**Multi-agent**
- Multiple agents connected simultaneously; switch with voice or keyboard
- Each agent in its own terminal
- Agent announce via TTS when switching

**OpenVIP protocol**
- Dictare is a reference implementation of the
  [OpenVIP](https://github.com/openvip-dev/protocol) open protocol
- Any tool can connect as an agent using the OpenVIP SDK

**Dashboard**
- Web UI served from the engine (no Electron, no separate process)
- Install/manage STT and TTS engines
- Live status, agent view, settings editor

**CLI**
- `dictare service install/start/stop/status` — service lifecycle
- `dictare agent <name>` — launch agent session
- `dictare speak <text>` — send TTS request to running engine
- `dictare status` — engine health and connected agents
- `dictare logs` — tail engine and TTS worker logs

**Operating Systems**
- macOS — fully supported; menu bar tray icon, global hotkey
- Linux — fully supported; system tray, systemd service
- Windows — early experimentation
