# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.5] - 2026-03-28

### Changed
- Linux install script rewritten with two-phase approach: checks prerequisites first (prints commands, exits), then installs user-space only (no sudo)
- PyGObject added as optional `[tray]` dependency — survives upgrades, no manual pip install needed
- `dictare status` shows "—" instead of "FAIL" for optional components (e.g. NVIDIA GPU on non-GPU machines)
- `dictare setup` and install script say `my-first-session` instead of `claude`

### Fixed
- ydotool 0.1.x (Ubuntu 24.04) compatibility — works without ydotoold daemon
- PyGObject install in uv tool venv — uses `uv pip install` instead of broken `python -m pip`
- PATH warning now shows correctly after uv install
- Agent CLI checks if profile binary is installed before launching, shows available profiles

## [0.2.4] - 2026-03-27

### Fixed
- Service restart now properly stops the engine process, not just the launcher

## [0.2.3] - 2026-03-26

### Fixed
- Agent claim key (CTRL+\) now handles all terminal key encodings, fixing compatibility with recent Claude Code versions
- Control endpoint responses now comply with the OpenVIP protocol (missing `openvip` field)

## [0.2.2] - 2026-03-20

### Added
- `live_dangerously` config default for agent profiles — set globally in `[agent_profiles]` or per-profile to skip `--live-dangerously` CLI flag

### Fixed
- Focus-triggered audio reconnect loop after sleep/wake — rapid focus cycling caused infinite reconnect attempts, leaving STT unresponsive despite agent showing as connected

## [0.2.1] - 2026-03-16

### Changed
- Replace `verbose` config flag with `log_level` (debug/info/warning/error). `--verbose` CLI flag kept as alias.

### Fixed
- Service logs now include timestamps on all stderr output (including startup crashes)
- Self-healing: engine auto-updates `python_path` on startup (fixes `brew upgrade` path mismatch)
- Simplified Homebrew formula — no more sandbox permission errors on install/upgrade

## [0.2.0] - 2026-03-16

First public release. Strict semver from this point forward.

### Added
- 556 new tests (1772 total, 58% coverage)
- Permissions documentation for macOS (3 steps) and Linux (evdev + ydotool)
- Mute/unmute voice commands in README

### Changed
- README rewritten for public launch
- OpenVIP URLs standardized to openvip.dev
- Language order: EN, DE, ES, IT, FR

### Fixed
- Regenerated up-beep.wav
- mypy type annotation in controller.py
- test_settings_api isolated from local config

## [0.2.0b3] - 2026-03-14

### Changed
- `agent_types` renamed to `agent_profiles` across config, CLI, UI, and docs
- CLI: `--profile` is the primary flag, `--type` kept as alias for backward compatibility
- Default STT model: parakeet-v3 → large-v3-turbo (wider language support, better known)
- Models UI: trimmed to large-v3-turbo, large-v3, parakeet-v3

### Fixed
- FSM race condition: TTS announcements during RECORDING/TRANSCRIBING no longer deadlock the engine

## [0.2.0b2] - 2026-03-14

### Added
- "Launch at login" toggle moved to General tab (more discoverable)
- Overview page in documentation

### Changed
- Settings UI: added General tab (launch at login, output mode, verbose), removed Output/Logging/Daemon sub-tabs
- Settings UI: hidden non-essential fields (redact, socket_path, log_file, editor, typing_wpm, silence_ms, translate, tts.speed, keyboard.shortcuts)
- Settings UI: clearer labels — "Speech language hint", "Voice accent", "Speaker", "Default output mode"
- Config defaults: silence_ms 1200→850, sound volumes 0.3, claude --max-turns 1000
- Config defaults: mute/listen triggers enabled with mate/buddy variants
- Config defaults: agent_filter enabled, claim_key explicit
- Tray: "Target" renamed to "Current" for consistency with codebase
- Removed Coqui TTS engine from status listing
- Status CLI: wider column alignment for engine names

### Fixed
- `dictare transcribe --auto-submit` now exits after first transcription (one-shot, pipe-friendly)
- Hotkey: Cmd+click no longer false-triggers on macOS (mouse events added to CGEventTap)

## [0.2.0b1] - 2026-03-14

First public beta. Voice layer for AI coding agents — the reference implementation
of the [OpenVIP](https://github.com/openvip-dev/protocol) open protocol.

**Why 0.2.0?** The 0.1.x series (0.1.0 through 0.1.140, 1200+ commits) was
internal development and dogfooding — used daily for real work, but never
publicly released. Starting from 0.2.0, Dictare follows strict semver:
features bump minor, fixes bump patch, breaking changes bump major.
We'll go to 1.0.0 when the API is stable and battle-tested by the community.

### Highlights

- **Voice-to-Agent delivery** — speak to Claude Code, Codex, Gemini, Aider, or any
  CLI tool. Transcriptions are routed via the OpenVIP protocol, not keystrokes.
- **No focus required** — your agent receives voice even when its window is in the
  background. No alt-tab needed.
- **100% local** — STT and TTS run entirely on your machine. Zero data leaves your
  computer. No cloud, no API keys, no subscription.
- **Multi-engine STT** — Whisper (MLX on Apple Silicon, CTranslate2 on Linux/Intel),
  Parakeet v3 (ONNX, 25 languages). Hardware-accelerated, zero cold-start.
- **Multi-agent** — switch agents by voice (*"agent claude"*, *"agent codex"*).
  Each agent in its own terminal, all connected simultaneously.
- **Bidirectional** — TTS feedback (agent announcements, mute/unmute confirmation).
  Engines: espeak, macOS say, Piper, Kokoro.
- **Pipeline architecture** — composable filters and executors for submit detection,
  voice mute, agent switching. Fully configurable triggers.
- **System service** — runs at login via launchd (macOS) / systemd (Linux). Preloads
  models for instant response.
- **Signed + notarized macOS launcher** — proper Input Monitoring support, no
  Accessibility permission needed.
- **Web dashboard** — browser-based settings UI served from the engine.
- **CLI** — `dictare agent`, `dictare speak`, `dictare transcribe`, `dictare service`,
  `dictare status`, `dictare logs`, `dictare models`.
- **Pipe-friendly** — `dictare transcribe | llm | dictare speak`.
- **Cross-platform** — macOS (Intel + Apple Silicon) and Linux (X11 + Wayland).

### Changed (since 0.1.x series)

- Version scheme: moved from 0.1.x rapid iteration to 1.0.0 semver
- macOS hotkey: Cmd+click no longer false-triggers dictare

## [0.1.140rc17] - 2026-03-14

### Fixed
- Audio feedback volume now applies to TTS announcements (agent switch)

## [0.1.140rc16] - 2026-03-14

### Added
- Scroll region auto-detection: agents that use their own DECSTBM sequences
  (Codex, Gemini) are automatically switched to `scroll_region=false` at
  runtime — no manual `[agent_types.*.terminal]` config needed

### Fixed
- Status bar no longer duplicated on terminal resize (stale row cleanup)
- `on_resize()` no longer writes to stdout from SIGWINCH handler
  (fixes `RuntimeError: reentrant call` crash)
- `request_redraw()` now only fires in scroll_region mode — prevents
  cursor save/restore interference with agents during rapid resize

### Changed
- Simplified default agent types: Claude, Codex, Gemini, Aider
- Removed hardcoded `scroll_region=false` from Codex/Gemini defaults
  (handled by auto-detection)

## [0.1.140rc13] - 2026-03-12

### Fixed
- Improved status bar stability for Codex and Gemini CLI
- Status bar no longer disappears at Codex startup or after interactions
- Eliminated spinner line accumulation and duplicate content in Gemini CLI
- Homebrew install script reliability improvements

### Changed
- Improved status bar redraw strategy for better compatibility across agent CLIs
- Gemini CLI: corrected `continue_args` to `["--resume", "latest"]`, added `--yolo` support
- Added Aider to default agent types

## [0.1.140rc12] - 2026-03-12

### Fixed
- Agent switch to already-current agent no longer triggers TTS announcement

### Changed
- Cleaner agent CLI logging (banner moved to log file, removed `--quiet`)
- Agent logs available via `dictare logs --name agent.{name}`
- Improved test suite performance and coverage

## [0.1.140rc11] - 2026-03-11

### Added
- Linux mode switch modifier: hold Right Alt + hotkey to toggle agent/keyboard mode (parity with macOS)

### Fixed
- Homebrew install script reliability improvements

### Changed
- UI: improved dark mode input/select border visibility

## [0.1.140rc10] - 2026-03-11

### Changed
- GitHub Actions pipeline testing — Infisical secrets integration

## [0.1.140rc8] - 2026-03-11

### Changed
- Deployment pipeline test

## [0.1.140rc7] - 2026-03-11

### Changed
- Homebrew formula now includes signed launcher as resource (no external scripts needed)
- `dictare service install` auto-detects launcher from Homebrew Cellar

## [0.1.140rc6] - 2026-03-11

### Added
- `dictare transcribe` command — registers as OpenVIP agent, prints transcriptions to stdout
- Accumulate mode (default): buffers text, prints on submit, then exits (one-shot)
- `--auto-submit` mode: prints each transcription immediately (Ctrl+C to stop)
- `--verbose` / `-v` flag on `transcribe` and `speak` — echo text to stderr (useful in pipes)
- Pipe-friendly: `dictare transcribe | llm | dictare speak`

## [0.1.140rc5] - 2026-03-10

### Changed
- CI: auto-update Homebrew tap after PyPI publish (deployment pipeline test)

## [0.1.140rc4] - 2026-03-10

### Changed
- UI: hide incomplete keyboard shortcuts feature (work in progress)

## [0.1.140rc3] - 2026-03-10

### Added
- Terminal output redaction for demos (`redact` config field)
- Tests for redaction feature

## [0.1.140] - 2026-03-09

### Changed
- CI builds complete signed+notarized+stapled `.app` bundle (not just the binary)
- `python_path` moved to `~/.dictare/python_path` — signed bundle stays immutable across brew upgrades
- `install.sh` downloads and installs the complete `.app` bundle from GitHub Release
- Swift launcher reads `python_path` from `~/.dictare/` first, falls back to bundle (backward compat)

## [0.1.139] - 2026-03-08

### Added
- Mode switch modifier: hold a secondary key while tapping the hotkey to toggle between agent and keyboard mode

## [0.1.138] - 2026-03-07

### Changed
- `auto_submit` setting now visible in UI under Output (was hidden)
- `auto_submit` description corrected: works in both agent and keyboard mode

## [0.1.137] - 2026-03-06

### Changed
- Agent session summary now shows detailed stats (timing breakdown, effective WPM, time saved, lifetime stats)

## [0.1.136] - 2026-03-06

### Added
- Auto-populate STT hotwords from pipeline trigger words for better recognition

### Fixed
- Script paths after reorganization
- CI notarization timeout

## [0.1.135] - 2026-03-06

### Changed
- Bundle ID renamed to `dev.dragfly.dictare`

### Added
- Signed and notarized macOS launcher (automated CI pipeline)
- Pre-built launcher support in `service install`

## [0.1.134] - 2026-03-05

### Fixed
- Hotkey combo detection on macOS: modifier+key combos (e.g. Cmd+I) no longer trigger dictare

## [0.1.133] - 2026-03-05

### Fixed
- Agent mode: skip VAD/transcription when no agents connected (zero CPU idle)

## [0.1.132] - 2026-03-05

### Fixed
- Double-tap submit now waits for speech to finish before sending
- Status bar and tray show "recording" state during active speech
- Faster audio recovery after sleep/wake (~3s instead of 15s+)

## [0.1.130] - 2026-03-05

### Fixed
- Tray app now shows "Muted" state correctly
- Mute filter settings visible in Settings UI

## [0.1.129] - 2026-03-05

### Added
- Voice mute/unmute commands: "OK mute" silences voice input, "OK listen" resumes
- TTS feedback phrases on mute/unmute
- TTS precache for instant playback

### Changed
- API state "idle" renamed to "off"
- Voice-muted state reported as "muted" in status API

## [0.1.128] - 2026-03-05

### Changed
- Double-tap during recording now waits for transcription to complete before submitting

## [0.1.127] - 2026-03-04

### Added
- Pipe `|` syntax for submit filter triggers: `["ok|okay", "send|submit"]` matches any combination
- Default submit trigger enabled out of the box: "ok send" / "okay submit" (wildcard, all languages)

### Fixed
- Favicon now renders correctly (static file instead of data URI)

## [0.1.126] - 2026-03-04

### Fixed
- Favicon now shows purple (#6d5ce6) Dictare icon using base64-encoded SVG (fixes missing favicon)
- Updated app_icon.svg to match brand color

## [0.1.125] - 2026-03-04

### Fixed
- Hotkey and other string fields no longer show as "modified" (amber) when using the platform default
- KeyCaptureField shows the resolved default key with "(default)" label when not explicitly configured

## [0.1.124] - 2026-03-04

### Fixed
- Audio recovery after Mac sleep/wake
- `dictare speak stop` no longer crashes when no TTS is playing
- Favicon now shows the actual Dictare icon

## [0.1.123] - 2026-03-04

### Fixed
- Focus-gated sounds survive engine restart
- Sound config defaults preserved when partially configured
- Multiple browser tabs no longer exhaust SSE connections

### Changed
- Submit sound simplified to single typewriter burst
- Only one Settings tab active at a time

## [0.1.122] - 2026-03-04

### Fixed
- Remove long-press hotkey gesture — interfered with modifier key combos (e.g. Cmd+Arrow)
- Agent filter no longer matches reserved internal agents (`__keyboard__`, `__tts__`); saying "agent keyboard" no longer switches to keyboard mode
- "In use" output device label now shows actual fallback device when configured device is unavailable

### Changed
- Output mode toggle (agents/keyboard) is now UI-only

## [0.1.121] - 2026-03-04

### Fixed
- Audio device dropdowns now update live when devices change
- Instant-save for audio device selection
- Device list updates work across all settings tabs

## [0.1.120] - 2026-03-04

### Added
- Live audio device monitoring: detect add/remove and default device changes
- Instant audio device switching from Settings UI (no engine restart)
- UI auto-updates when devices change

### Changed
- UI assets properly cached (fixes stale UI after upgrade)

## [0.1.119] - 2026-03-04

### Fixed
- Tray icon flickering every second on Linux — skip icon/menu updates when state is unchanged

## [0.1.118] - 2026-03-04

### Changed
- Settings UI loads faster (single fetch for all data)
- Dashboard: agent switch is instant
- EngineStatusBar: loading state amber, ready state purple

### Fixed
- Dashboard live updates now work correctly
- Save no longer flickers values during engine restart

## [0.1.117] - 2026-03-04

### Changed
- Settings UI: unified save UX — any change shows one SaveBar, Save auto-restarts engine

## [0.1.116] - 2026-03-04

### Fixed
- Terminal focus detection no longer flickers during text injection

## [0.1.115] - 2026-03-03

### Changed
- `transcribed` sound default volume raised from 0.15 to 1.0

## [0.1.114] - 2026-03-03

### Changed
- Submit typewriter burst trimmed to exactly 1 second (`typewriter-burst.wav`)

## [0.1.113] - 2026-03-03

### Added
- New `submit` sound event: typewriter burst on double-tap/submit, independently configurable (volume 0.25, not focus-gated)

### Changed
- Submit sequence uses dedicated `submit` event instead of reusing `transcribing`
- `transcribing` default volume set to 0.15 (subtle background sound when enabled)

## [0.1.112] - 2026-03-03

### Fixed
- Submit sequence: typewriter burst now always plays (was skipped when `transcribing` sound disabled)
- About dialog: use NSAlert instead of `orderFrontStandardAboutPanel_` — works in accessory mode; log errors at warning level

## [0.1.111] - 2026-03-03

### Changed
- pencil-write sound now randomly picks from 5 bundled clips for variety

## [0.1.110] - 2026-03-03

### Changed
- **Submit sound is now typewriter + carriage-return sequence** — double-tap and
  pipeline submit play a short typewriter burst followed by carriage-return,
  matching the typewriter metaphor. Carriage-return never plays alone.

## [0.1.109] - 2026-03-03

### Fixed
- **"sent" sound only on submit** — carriage-return was incorrectly playing after
  every transcription. Now only fires on double-tap submit and pipeline submit trigger.

### Changed
- **pencil-write.wav** — replaced synthesized placeholder with real pencil scratch
  sound (freesound_community via Pixabay).

### Added
- **About dialog in tray app** — shows Dictare version, description, and sound
  credits loaded from `credits.json`. Uses native macOS about panel on macOS,
  tkinter fallback on Linux.
- **credits.json** — structured attribution file for bundled assets.

## [0.1.108] - 2026-03-03

### Added
- **Focus-aware audio feedback** — sounds are silenced when the terminal has focus (you can already see the text)
- **"transcribed" sound** — subtle pencil-on-paper after each transcription (focus-gated)
- **"sent" sound** — carriage-return plays on text submission
- Per-sound `focus_gated` config

### Changed
- Renamed `ready.wav` → `carriage-return.wav`

## [0.1.107] - 2026-03-03

### Fixed
- Non-default indicator (amber dot) now only shows on dropdown fields where appropriate

## [0.1.106] - 2026-03-03

### Changed
- Hotkey gestures swapped: double tap submits, long press toggles agent/keyboard mode

## [0.1.105] - 2026-03-03

### Fixed
- `dictare agent` now validates engine and agent name before launching (no more stuck terminals)
- Auto-start engine waits for readiness before proceeding

## [0.1.104] - 2026-03-03

### Changed
- Default STT model changed to parakeet-v3 (faster, lighter, comparable accuracy)
- Removed obsolete STT models (tiny, base, small, medium)

## [0.1.103] - 2026-03-03

### Fixed
- Non-default indicator now correctly shows for explicitly set values

## [0.1.102] - 2026-03-03

### Changed
- Standby status bar color reflects mic state (gray when inactive, yellow when listening)

## [0.1.101] - 2026-03-03

### Fixed
- Non-default indicator no longer shows false positives for default values

## [0.1.100] - 2026-03-03

### Fixed
- Settings dropdowns show "Default" correctly after save
- Settings values update when switching between sections

## [0.1.96] - 2026-03-02

### Fixed
- Tray "Start/Stop Service" now correctly reflects engine state
- Tray survives reinstall without losing icon

## [0.1.95] - 2026-03-02

### Fixed
- Tray "Start/Stop Service" stays in sync when service is controlled externally

## [0.1.94] - 2026-03-02

### Changed
- Default STT model changed to `large-v3-turbo` (GPU-accelerated on Apple Silicon)

## [0.1.93] - 2026-03-02

### Fixed
- VAD startup 400x faster (~0.05s instead of 20s+ on first run after install)

## [0.1.92] - 2026-03-02

### Added
- Granular timing logs for audio startup diagnostics

## [0.1.91] - 2026-03-02

### Fixed
- Tray install no longer shows spurious "Unload failed" errors

## [0.1.90] - 2026-03-02

### Fixed
- macOS install script no longer causes engine restart loop during Homebrew reinstall

## [0.1.89] - 2026-03-02

### Added
- Unified select component in Settings UI (replaces separate preset, enum, and device selectors)
- Settings can now be reverted to default by clearing the value

### Removed
- Separate `DeviceField`, `PresetField`, `EnumField` components (merged into one)

## [0.1.88] - 2026-03-02

### Added
- Settings presets API: UI now shows "Default (value)" labels and backend-driven option lists
- Settings UI field registry is now fully auto-generated

### Fixed
- Stale `auto_enter` reference in UI field config (renamed to `auto_submit`)

## [0.1.87] - 2026-03-02

### Changed
- Input operations now support multiple actions per message (e.g. newline + submit)
- openvip SDK bumped to `>=1.0.0rc10` (resolved from PyPI)

### Fixed
- Dashboard API calls pointed to wrong URL paths

## [0.1.86] - 2026-03-02

### Fixed
- CLI commands (`status`, `service`, `speak`) now use correct API base path
- Install script path corrections after repo reorganization

## [0.1.85] - 2026-03-02

### Changed
- URL structure: OpenVIP protocol endpoints at `/openvip/`, management endpoints at `/api/`
- OpenVIP spec served at `/openvip/openapi.json` for API discovery
- `auto_enter` renamed to `auto_submit` in config

## [0.1.82] - 2026-03-01

### Changed
- Default output mode is now `agents` (was `keyboard`)
- Keyboard typing delay lowered from 5ms to 2ms
- Keyboard-only settings moved from Output tab to Keyboard tab

## [0.1.81] - 2026-02-28

### Added
- Session stats (transcriptions, words, audio duration) shown in foreground panel

## [0.1.80] - 2026-02-28

### Fixed
- Hotkey capture in settings now only accepts modifier keys (which is what macOS supports)

## [0.1.79] - 2026-02-28

### Changed
- Daily stats now tracked separately from historical totals, with automatic day rollover

## [0.1.78] - 2026-02-28

### Added
- Session stats summary printed when agent session ends
- Session stats shown in dashboard Engine card

## [0.1.77] - 2026-02-28

### Fixed
- Hotkey delivery metrics now tracked consistently for all event types

## [0.1.76] - 2026-02-28

### Fixed
- Long press submit now works from any app in agents mode (not just terminal)

## [0.1.75] - 2026-02-28

### Fixed
- Long press submit fires on key release instead of timeout (prevents Cmd+Return conflicts)

## [0.1.74] - 2026-02-28

### Fixed
- Input Monitoring permissions no longer lost after reinstall on macOS Sequoia

## [0.1.73] - 2026-02-28

### Changed
- Hotkey is now configurable without rebuilding the launcher — reads from config at startup
- Launcher sends key down/up events; gesture detection (tap, double-tap, long press) handled in Python
- Long press (≥ 0.8s): submits to agent. Double tap: toggles mode. Single tap: toggles mute.

## [0.1.72] - 2026-02-28

### Changed
- Dashboard: reordered Engine card rows for better alignment with Permissions column

## [0.1.71] - 2026-02-28

### Fixed
- Auto-cleanup of stale permission entries after launcher binary changes

## [0.1.70] - 2026-02-28

### Fixed
- Keyboard mode now reports actual injection success instead of false positives

## [0.1.69] - 2026-02-28

### Fixed
- Accessibility permission status no longer shows false negatives

## [0.1.68] - 2026-02-28

### Added
- Hard-reset script for macOS permissions and runtime state

### Fixed
- More reliable accessibility permission detection

## [0.1.67] - 2026-02-28

### Fixed
- Permission Doctor no longer causes brief "engine disconnected" UI errors
- Better diagnosis prioritization for hotkey issues

### Changed
- Permission Doctor UI: guided intro, auto-refresh, explicit restart action

## [0.1.66] - 2026-02-28

### Added
- Permission Doctor: structured diagnosis with actionable steps and one-click fixes
- Tests for permission diagnosis

## [0.1.65] - 2026-02-28

### Added
- Permission Doctor: guided troubleshooting for hotkey and permission issues
- Dashboard links failed permissions directly to Permission Doctor
- Hotkey status API with runtime health information

### Changed
- Hotkey uses IPC (Unix socket) as primary transport, with signal fallback

## [0.1.64] - 2026-02-28

### Added
- Hotkey IPC transport (Unix socket with ACK) — more reliable than signals

### Fixed
- Hotkey delivery now confirmed by actual events, not just tap creation

## [0.1.63] - 2026-02-28

### Fixed
- Hotkey not working on macOS Sequoia despite Input Monitoring being granted (missing plist key)

## [0.1.62] - 2026-02-28

### Added
- Settings → Keyboard: hotkey status indicator with "Fix Input Monitoring" button

## [0.1.61] - 2026-02-28

### Fixed
- Hotkey recovery after macOS disables the event tap (recreate instead of re-enable)

## [0.1.60] - 2026-02-28

### Fixed
- Tray always showed "Disconnected" when launched as a service

### Added
- `dictare logs --tray` to view tray logs

## [0.1.59] - 2026-02-28

### Fixed
- Tray service install/upgrade reliability improvements

## [0.1.58] - 2026-02-28

### Added
- `service install` now sets up both engine and tray automatically
- Homebrew `post_install` runs `service install` — zero-config for new users
- Settings → Advanced: "Launch at login" toggle

## [0.1.57] - 2026-02-28

### Changed
- Launcher ensures tray is running on startup
- Tray LaunchAgent survives `brew upgrade` without re-running `service install`

## [0.1.56] - 2026-02-27

### Changed
- Dashboard UI refinements: clickable agent pills, cleaner status indicators, better layout

## [0.1.55] - 2026-02-27

### Added
- Models page: delete button to remove downloaded model files and venvs

## [0.1.54] - 2026-02-27

### Added
- Light/dark/system theme toggle in settings sidebar
- Updated wordmark to match dictare.io branding

## [0.1.53] - 2026-02-27

### Fixed
- Engine crash when pressing hotkey during startup (model loading phase)

## [0.1.52] - 2026-02-27

### Changed
- Tray uses HTTP polling instead of SSE — eliminates stuck state bugs after engine restart

## [0.1.51] - 2026-02-27

### Fixed
- Dashboard: correct hotkey status colors and permission display
- Engine correctly reads hotkey status from launcher in daemon mode

## [0.1.50] - 2026-02-27

### Fixed
- MLX Whisper: corrected model repository IDs for all sizes

## [0.1.49] - 2026-02-27

### Fixed
- MLX Whisper: fallback model repository also corrected

## [0.1.48] - 2026-02-27

### Fixed
- Permission status now correctly reflects actual hotkey and accessibility state

## [0.1.47] - 2026-02-27

### Fixed
- `service install` no longer blocks waiting for permission dialog

## [0.1.46] - 2026-02-27

### Added
- Launcher diagnostic logging for hotkey events
- Hotkey status confirmed only after real event delivery (not just tap creation)

## [0.1.45] - 2026-02-27

### Changed
- Launcher logs engine exit details for easier debugging

## [0.1.44] - 2026-02-27

### Changed
- Models page: compact table layout (STT/TTS) replacing vertical cards
- Faster engine status polling (1s instead of 2s)

## [0.1.43] - 2026-02-27

### Fixed
- CSS missing on Linux after `git pull` (gitignore was too broad)

## [0.1.42] - 2026-02-27

### Fixed
- Linux: service stop no longer hangs for 90s (10s timeout + force-kill fallback)

## [0.1.41] - 2026-02-27

### Changed
- Dashboard: Engine (left) | Permissions (right), Agents full-width below

## [0.1.40] - 2026-02-27

### Changed
- Rebuilt UI with updated icon

## [0.1.39] - 2026-02-27

### Changed
- Settings nav: added Dictare icon

## [0.1.38] - 2026-02-27

### Changed
- New official brand icons for tray and app (purple mic/squircle)

## [0.1.37] - 2026-02-27

### Changed
- Improved TTS error messages and logging

## [0.1.36] - 2026-02-27

### Changed
- Code quality: tighter exception handling, named constants, better logging

## [0.1.35] - 2026-02-27

### Changed
- TTS flow aligned with OpenVIP spec naming (`message_id`)
- Model selection no longer auto-restarts engine — user decides when to restart
- Event queue no longer drops events silently

## [0.1.34] - 2026-02-27

### Added
- Tray menu: Start/Stop Service under Advanced

## [0.1.33] - 2026-02-27

### Fixed
- Newline regression: transcriptions no longer broke across lines (SDK extension field issue)
- `dictare speak stop` / `--timeout` now uses openvip SDK properly

### Added
- Install scripts: `full-install.sh` (dev), `install.sh` (app), platform auto-detect

## [0.1.32] - 2026-02-26

### Fixed
- `dictare speak --timeout`: correct error message on timeout vs engine down

## [0.1.31] - 2026-02-26

### Added
- `dictare speak stop` — interrupt TTS audio mid-playback
- `dictare speak --timeout` — configurable request timeout (default 300s)

## [0.1.30] - 2026-02-26

### Fixed
- TTS worker crash on startup (auth token format issue)

## [0.1.29] - 2026-02-26

### Fixed
- `dictare speak -l` language override now respected correctly

## [0.1.28] - 2026-02-26

### Fixed
- Kokoro TTS: non-English voices now use correct phonetics (voice prefix determines language)

## [0.1.27] - 2026-02-26

### Fixed
- Speech API response now passes SDK validation

## [0.1.26] - 2026-02-26

### Fixed
- TTS worker no longer crashes on speech requests (SDK compatibility fix)

## [0.1.25] - 2026-02-26

### Fixed
- `dictare speak` now works correctly (SDK was missing required message fields)

## [0.1.24] - 2026-02-26

### Fixed
- Tray no longer shows "Disconnected" on first startup before engine is ready

## [0.1.23] - 2026-02-26

### Changed
- openvip SDK now resolved from PyPI — no more local tarball needed

## [0.1.22] - 2026-02-26

### Fixed
- App icon shows correctly in macOS permission dialogs
- Install script now auto-starts service on fresh install

## [0.1.21] - 2026-02-26

### Added
- Test coverage for session helpers and stats persistence (46 new tests)

## [0.1.20] - 2026-02-26

### Added
- Test coverage for status bar (17 new tests)

## [0.1.19] - 2026-02-26

### Added
- OpenVIP v1.0 message validation — non-compliant payloads rejected with clear error

## [0.1.18] - 2026-02-26

### Added
- Current directory shown in status bar

### Changed
- Alignment with OpenVIP v1.0 spec

## [0.1.17] - 2026-02-26

### Added
- Agent type or command shown in status bar

## [0.1.16] - 2026-02-26

### Fixed
- Hotkey capture in settings now works on macOS

## [0.1.15] - 2026-02-26

### Fixed
- Launching the same agent session twice now exits with a clear error

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
