# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.19] - 2026-02-26

### Added
- OpenVIP v1.0 message validation on `/agents/{id}/messages` and `/speech`
  endpoints — non-compliant payloads are rejected with 422 and a clear
  "Not OpenVIP v1.0 compliant" error message
- Bundled OpenVIP v1.0 JSON Schema (`fastjsonschema`, compiled, ~2μs/call)
- 55+ invalid-message test cases covering missing fields, wrong types,
  bad versions, enum violations, confidence bounds, extension type checks,
  and dependentRequired constraints

## [0.1.18] - 2026-02-26

### Changed
- Alignment with OpenVIP v1.0 spec

## [0.1.18] - 2026-02-26

### Added
- Current directory shown in status bar right side — `~/repos/proj · [opus] · dictare 0.1.18`;
  home prefix replaced with `~`, long paths truncated from the left with `…`

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
