# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
