# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
