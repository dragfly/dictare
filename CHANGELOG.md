# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0-alpha.108] - 2026-02-11

### Fixed

- CI: checkout OpenVIP SDK via PAT token + `actions/checkout` (cross-org access).
- CI: use `--no-sources` flag for uv install (ignore local `[tool.uv.sources]`).
- CI: lint only `src/` and `tests/` (avoid linting generated SDK code).
- Flaky test `test_speech_end_starts_watchdog`: use `_wait_until` for watchdog startup.

## [3.0.0-alpha.107] - 2026-02-11

### Added

- `openvip` SDK as project dependency — the official OpenVIP Python client.
- Local development source configured via `[tool.uv.sources]` pointing to
  `openvip-sdks/python` repo.

### Changed

- `cli/speak.py`: replaced manual `urllib` HTTP calls with `openvip.Client.speak()`.
  Platform-specific TTS params (engine, voice, speed) passed via `**kwargs`.
- `tray/app.py`: replaced manual `urllib` polling and control calls with
  `openvip.Client.get_status()` and `openvip.Client.control()`.

## [3.0.0-alpha.106] - 2026-02-11

### Changed

- Default OpenVIP HTTP port changed from 8765 to 8770 to avoid conflict with
  Python websockets library convention. Affects config, http_server, agent/mux,
  panel, tray, and speak CLI.

## [3.0.0-alpha.105] - 2026-02-11

### Removed

- Entire `daemon/` module (~1640 lines) — Unix socket server, client, protocol,
  lifecycle management. All functionality already provided by `core/` HTTP API
  (FastAPI OpenVIPServer on `/status`, `/control`, `/speech`).
- `cli/daemon.py` — `voxtype daemon start/stop/status/restart` commands removed.

### Changed

- `cli/speak.py`: uses HTTP `/speech` endpoint instead of daemon Unix socket.
- `tray/app.py`: polls engine via HTTP `/status` and controls via `/control`.
- `services/stt_service.py`, `services/tts_service.py`: removed daemon code
  paths, simplified to local engine only.

## [3.0.0-alpha.104] - 2026-02-11

### Changed

- Improved module docstrings for `core/` and `app/` to clarify architectural
  roles: core/ is the engine (VoxtypeEngine + OpenVIPServer + state machine),
  app/ is the orchestrator (AppController manages lifecycle and bindings).

## [3.0.0-alpha.103] - 2026-02-11

### Removed

- Dead `LocalReceiver` class (`output/local.py`) — never instantiated in
  production, duplicated `KeyboardAgent` functionality. Removed along with
  its 20 tests.

## [3.0.0-alpha.102] - 2026-02-11

### Removed

- Dead `engine/` module — scaffolding never completed, `Engine` class never
  instantiated, zero tests. Only `get_pid_path()` was used externally, moved
  to `utils/paths.py`. Runtime unchanged (core/ is the real engine).

## [3.0.0-alpha.101] - 2026-02-11

### Changed

- Extract `PTYSession` class from `mux.py` into `pty_session.py` — isolates
  PTY lifecycle (openpty, fork+exec, SIGWINCH, output loop, cleanup) from
  orchestration concerns (SSE, status bar, session logging, raw mode).
  `run_agent()` becomes a thin orchestrator. Public API unchanged.

## [3.0.0-alpha.100] - 2026-02-11

### Removed

- Parked web PTY features for go-live cleanup: terminal viewer (`--tv` flag),
  multi-agent server (`voxtype multiagent`), and headless agent. Code moved
  to `_parked/web-pty/` with README for re-insertion instructions. These are
  experimental features that will be restored in a future release.

## [3.0.0-alpha.99] - 2026-02-11

### Added

- `voxtype config edit` — opens config file in your editor. Respects
  `editor` config field, `$VISUAL`, `$EDITOR`, or falls back to platform
  default (`open -t` on macOS, `xdg-open` on Linux). Creates default
  config if file doesn't exist. Config file includes commented examples
  for common editors (vim, nano, VS Code, Sublime Text).

## [3.0.0-alpha.98] - 2026-02-11

### Fixed

- CI: fix mypy `attr-defined` errors on `uvicorn.Server.should_exit` in
  terminal_viewer.py and multiagent_server.py (wrong type: ignore code).
- CI: fix mypy `assignment` error in mux.py duplicate agent error path.

## [3.0.0-alpha.97] - 2026-02-11

### Fixed

- Agent with duplicate name now shows clear error instead of retrying forever.
  `_read_from_sse()` catches HTTP 409 separately from transient network errors
  and exits immediately with `"✖ Agent 'name' already connected"` on the status
  bar. Previously, `HTTPError` was caught as `URLError` (its parent class) and
  treated as a reconnectable error, causing an infinite retry loop.

## [3.0.0-alpha.96] - 2026-02-11

### Added

- Granular audio feedback configuration via TOML sub-tables. Each sound event
  (start, stop, transcribing, ready, sent, agent_announce) can be individually
  enabled/disabled and assigned a custom sound file path without losing settings.
  Master switch `audio_feedback` still controls all sounds globally.

  ```toml
  [audio.sounds.transcribing]
  enabled = false

  [audio.sounds.start]
  enabled = true
  path = "/custom/beep.mp3"
  ```

### Changed

- Replaced flat `sound_start`/`sound_stop`/`sound_transcribing`/`sound_ready`
  config fields with structured `[audio.sounds.*]` sub-tables.

## [3.0.0-alpha.95] - 2026-02-11

### Added

- Piper TTS auto-downloads voice models from HuggingFace on first use.
  Models stored in `~/.local/share/piper-voices/`. Download happens during
  engine startup (with progress bar), not at first speak.

### Fixed

- Piper TTS: install `pathvalidate` alongside `piper-tts` (missing upstream
  dependency causes `ModuleNotFoundError` on macOS).
- Piper TTS: pass full ONNX model path instead of voice name (fixes
  "Unable to find voice" error).
- `install.sh` now runs `voxtype dependencies resolve` after installation
  to re-install optional dependencies (e.g., piper-tts) that `uv tool install`
  removes during upgrade.
- SSE agent test `test_sse_connect_sets_event` no longer blocks for 60s —
  mocked `urllib.request.urlopen` instead of real HTTP server. Full suite
  dropped from ~70s to ~9s.

## [3.0.0-alpha.91] - 2026-02-11

### Changed

- TTS error in panel now shows actionable fix: `voxtype dependencies resolve`
  instead of raw `uv pip install` command.
- `voxtype dependencies resolve` now installs optional dependencies too
  (configured TTS engine: piper-tts, TTS, mlx-audio, etc.).

## [3.0.0-alpha.90] - 2026-02-11

### Added

- TTS engine loaded at startup with progress bar, like STT and VAD.
  If the engine is unavailable (missing dependency), the panel shows
  the error with the install command inline.
- `voxtype dependencies check/resolve` now checks configured TTS engine
  dependencies (piper-tts, TTS, mlx-audio, etc.).
- `/status` HTTP endpoint includes `tts.available` and `tts.error` fields.
- `_handle_tts_request` returns JSON error when TTS engine unavailable.
- `_build_model_line` supports "error" status (red ✗).

## [3.0.0-alpha.89] - 2026-02-11

### Fixed

- Status panel now shows configured TTS engine and language (e.g.,
  `TTS: espeak (en)`) instead of hardcoded `(disabled)`.

## [3.0.0-alpha.88] - 2026-02-11

### Changed

- `POST /speech` now uses the TTS engine system (espeak, say, piper, coqui,
  outetts, qwen3) instead of raw subprocess calls. Request body accepts
  `engine`, `language`, `voice`, `speed` overrides with fallback to config.
- `speak_text()` delegates to `get_cached_tts_engine()` instead of shelling
  out to `say`/`espeak` directly.
- `_handle_tts_request()` returns accurate `duration_ms` (blocking call
  instead of fire-and-forget) and handles mic-pausing inline.

## [3.0.0-alpha.87] - 2026-02-10

### Fixed

- Multiagent: child process wrapped in try/except with `os._exit(127)` — if
  `chdir` or `execvp` fails the forked child no longer corrupts the parent.
- Multiagent: `_read_pty_output` catches `OSError` from `select.select` on
  closed fd — clean shutdown without traceback spam.
- Multiagent: validate `cwd` exists before forking (returns 400 to browser).

## [3.0.0-alpha.86] - 2026-02-10

### Changed

- Multiagent UI: redesigned with Pico CSS framework (dark mode, professional
  look). Click anywhere on a card to switch agent (removed ▶ button). Toolbar
  reworked as a compact header with form. Cards have hover/active transitions
  and accent border highlight.

## [3.0.0-alpha.85] - 2026-02-10

### Fixed

- Engine status endpoint now reports the **actual** STT device (after cuDNN
  fallback) instead of the configured device. Previously, missing cuDNN would
  silently fall back to CPU while the panel still showed "CUDA" in green.
- Status panel now warns when GPU is detected but not accelerated: shows
  `CPU` in yellow/red with hint `(GPU detected, run: ./install.sh --gpu)`
  instead of misleading green "CUDA". Same for Apple Silicon without MLX.

## [3.0.0-alpha.84] - 2026-02-10

### Fixed

- Multiagent: X button and Ctrl+C now work — `HeadlessAgent.stop()` uses
  non-blocking `waitpid(WNOHANG)` + SIGKILL fallback instead of blocking
  `waitpid(0)`. DELETE endpoint runs in executor to not block the async loop.

### Added

- Multiagent: keyboard input in `/current` view — type directly in the
  browser terminal (xterm.js `onData` → WS → PTY). Works like a real terminal.
- Multiagent: working directory field (`cwd`) in agent creation form.

## [3.0.0-alpha.83] - 2026-02-10

### Added

- `voxtype multiagent` command — web UI to manage multiple headless agents.
  Grid view (`/`) shows all agents with xterm.js terminals, full-screen view
  (`/current`) follows the active agent. Agents are created/removed from the
  browser. Click-to-switch calls engine `output.set_agent`. Each agent runs in
  a headless PTY with SSE input from the engine. New files: `headless.py`,
  `multiagent_server.py`, `cli/multiagent.py`.

## [3.0.0-alpha.82] - 2026-02-10

### Added

- Terminal viewer: 1 MB ring buffer replay — new clients/refresh see current
  screen state instead of blank screen. xterm.js re-processes the buffered
  escape sequences on connect.
- Terminal viewer: PTY size sync — server sends `cols x rows` on WebSocket
  connect and on terminal resize (SIGWINCH). xterm.js matches the real PTY
  dimensions exactly. Removed FitAddon (was causing size mismatch).

## [3.0.0-alpha.81] - 2026-02-10

### Added

- Web terminal viewer: stream PTY output to browser via WebSocket + xterm.js.
  Opt-in with `--tv PORT` flag on `voxtype agent` command (e.g. `voxtype agent
  claude --tv 8766 -- claude`). Opens `http://127.0.0.1:PORT` in browser to
  mirror the agent's terminal. Zero overhead when not enabled. Uses FastAPI +
  uvicorn in a daemon thread (same pattern as the engine HTTP server).

## [3.0.0-alpha.80] - 2026-02-10

### Added

- Audio feedback on state transitions: descending tone when RECORDING→TRANSCRIBING
  (processing), ascending tone when TRANSCRIBING→LISTENING (ready). Uses
  `play_sound_file_async()` (fire-and-forget, no mic pause). Bundled sounds:
  `transcribing.mp3` and `ready.mp3`. Configurable via `sound_transcribing` and
  `sound_ready` in audio config.
- StateController now fires `on_state_change` callback for RECORDING→TRANSCRIBING
  transition (was missing, needed for audio feedback).

## [3.0.0-alpha.79] - 2026-02-10

### Fixed

- PTY write: add 10ms grace period (`stop_event.wait(0.01)`) between text and
  ESC/enter writes. Without the delay, fast consecutive writes can land in the
  same kernel read buffer, causing the slave's input parser to discard text
  preceding ESC. The 10ms lets the slave consume the text before ESC arrives.
  Uses cancellable `stop_event.wait()` instead of `time.sleep()`.

## [3.0.0-alpha.78] - 2026-02-10

### Fixed

- PTY write: revert atomic write (a75) — text and ESC sequences must be
  separate os.write() calls. When combined in one buffer, the slave's input
  parser treats ESC as the start of a key sequence and discards preceding text.
  Now: text → tcdrain → alt_enter → tcdrain → enter → tcdrain (no sleep)

## [3.0.0-alpha.77] - 2026-02-10

### Fixed

- Agent status race condition: SSE thread no longer emits "connected" status
  directly. Instead, it signals a shared `sse_connected` Event that the poll
  thread checks to force a status refresh. This ensures only one thread
  (poll) controls the status display, eliminating "● connected" getting
  stuck when poll sees no state change.

## [3.0.0-alpha.76] - 2026-02-10

### Fixed

- Remove `time.sleep` from SSE tests: reconnect test down from 0.51s to 0.02s,
  poll test from 0.06s to 0.01s. Made `retry_delay` configurable in `_read_from_sse`
  (default 0.5s production, 0.01s in tests). Test suite median back to ~8.7s

## [3.0.0-alpha.75] - 2026-02-10

### Fixed

- PTY write atomicity: text, visual newline, and submit enter are now written
  as a single `os.write()` call instead of 3 separate writes with 100ms delays.
  Prevents partial message delivery if the slave process flushes its input
  buffer between writes (observed: text lost but enter arrives → empty submit)
- Removed `time` import from mux.py (no longer needed without inter-write sleeps)

## [3.0.0-alpha.74] - 2026-02-10

### Reverted

- VAD no longer runs during TRANSCRIBING/INJECTING (reverts a67): caused
  MLX Whisper infinite decoding on queued audio fragments, burning GPU and
  locking engine on TRANSCRIBING. VAD only active in LISTENING/RECORDING
- Audio queuing restored to TRANSCRIBING-only (reverts a68 broadening)

### Kept

- Transcription watchdog timer (a72) retained as generic safety net
- STT lock timeout retained to prevent thread pile-up
- Test rules in CLAUDE.md

## [3.0.0-alpha.73] - 2026-02-10

### Changed

- Rewrite watchdog tests: call `_on_transcription_timeout()` directly
  instead of using `time.sleep`, add test rules to CLAUDE.md

## [3.0.0-alpha.72] - 2026-02-10

### Fixed

- Engine stuck on TRANSCRIBING when MLX Whisper enters infinite decoding
  loop on queued audio fragments: added 30s watchdog timer in controller
  that forces state recovery, plus STT lock timeout to prevent thread pile-up

## [3.0.0-alpha.71] - 2026-02-10

### Changed

- Agent no longer exits if engine server is unreachable at startup; instead
  the subprocess starts immediately and the SSE thread retries connection
  with backoff, showing status in the status bar

## [3.0.0-alpha.70] - 2026-02-09

### Fixed

- SSE agent status stuck on "reconnecting" (red) after transient connection
  hiccup: SSE thread now emits "connected" status on successful reconnect,
  and polling thread resets `was_active` on error so next poll forces update

## [3.0.0-alpha.69] - 2026-02-09

### Fixed

- `_process_queued_audio` crash: `if not audio_data` on numpy array raises
  `ValueError`; replaced with `if audio_data is None or len(audio_data) == 0`

## [3.0.0-alpha.68] - 2026-02-09

### Added

- Tests for VAD-during-busy-states fix: `should_process_audio` property
  coverage for all states, speech-end queuing in TRANSCRIBING/INJECTING/PLAYING

## [3.0.0-alpha.67] - 2026-02-09

### Fixed

- VAD now runs during TRANSCRIBING/INJECTING states: speech arriving while
  transcribing is detected and queued instead of being silently discarded
- Queue audio in all non-idle busy states (not just TRANSCRIBING) for
  defensive coverage

## [3.0.0-alpha.66] - 2026-02-08

### Fixed

- Engine stops recognizing speech after prolonged silence or CPU spikes:
  audio callback treated benign `input_overflow` as fatal device error,
  triggering unnecessary stream reconnect and losing VAD state
- Add periodic VAD LSTM state reset after 5 minutes of continuous silence
  to prevent numerical drift in Silero hidden states

## [3.0.0-alpha.65] - 2026-02-08

### Changed

- Split monolithic `cli.py` (3141 lines) into `cli/` package with 17 modules:
  `__init__.py`, `_helpers.py`, `listen.py`, `engine.py`, `speak.py`,
  `transcribe.py`, `execute.py`, `agent.py`, `daemon.py`, `models.py`,
  `config.py`, `completion.py`, `dependencies.py`, `devices.py`, `logs.py`,
  `tray.py`, `misc.py`
- Sub-app groups (completion, daemon, models, etc.) use `app = typer.Typer()`
  pattern; top-level commands (listen, speak, etc.) use `register(app)` pattern
- All public API preserved: `from voxtype.cli import app, main`

## [3.0.0-alpha.64] - 2026-02-08

### Changed

- Simplify `voxtype logs` — single unified command replaces 6 subcommands:
  `voxtype logs` (list files), `voxtype logs <name>` (tail), `--raw`, `--path`
- Consistent help text across all CLI commands: trailing periods, uniform verb
  form ("Manage ..."), lowercase "voxtype" branding everywhere
- Remove `logs session` subcommand (obsolete)

## [3.0.0-alpha.63] - 2026-02-08

### Changed

- Rename CLI subcommand `voxtype log` to `voxtype logs` (follows docker/kubectl convention)

## [3.0.0-alpha.62] - 2026-02-08

### Added

- Homebrew formula (`packaging/homebrew/voxtype.rb`) for `brew install` on macOS
- Debian package build scripts (`packaging/deb/`) with build-deb.sh, control,
  postinst, prerm, postrm for .deb distribution
- install.sh VERSION synced to current release (3.0.0a61 -> 3.0.0a62)

## [3.0.0-alpha.61] - 2026-02-08

### Fixed

- CI: fix macOS test-macos job — use explicit venv creation + pip install
  instead of `uv sync` which didn't install the package on self-hosted runner

## [3.0.0-alpha.60] - 2026-02-07

### Fixed

- Agent status bar shows correct initial state on startup — removed
  intermediate "connected" status that was overriding the poll thread's
  listening/standby check

## [3.0.0-alpha.59] - 2026-02-07

### Fixed

- Agent status bar shows correct initial state (standby/listening) instead
  of always showing "listening" on startup

## [3.0.0-alpha.58] - 2026-02-07

### Fixed

- Status bar survives child full-screen redraws (e.g. Ctrl+O in Claude Code):
  scroll region is now re-established after every child output chunk, and a
  periodic redraw every 2s ensures the bar content is repainted

## [3.0.0-alpha.57] - 2026-02-07

### Added

- Active agent indicator in status bar: polls `/status` every 3s to show
  `● agent · listening` (green) when active or `○ agent · standby` (yellow)
  when another agent is selected

## [3.0.0-alpha.56] - 2026-02-07

### Added

- Clear terminal on `voxtype agent` start — prevents dirty screen when
  relaunching after Ctrl+C. Configurable: `[client] clear_on_start = true`

## [3.0.0-alpha.55] - 2026-02-07

### Fixed

- Status bar resize: re-establish scroll region after every chunk of child
  output during the resize window (child TUI resets `\x1b[r]` during redraw)

## [3.0.0-alpha.54] - 2026-02-07

### Fixed

- Status bar resize: repeated redraw (every 150ms for 1s) to survive child
  TUI apps that reset scroll region during their own redraw cycle

## [3.0.0-alpha.53] - 2026-02-07

### Added

- `[client] status_bar = true/false` config option for status bar
  (`--no-status-bar` CLI flag overrides config)

## [3.0.0-alpha.52] - 2026-02-07

### Changed

- Extract status bar into `agent/status_bar.py` — isolated `StatusBar` class,
  mux.py stays clean. Disable with `--no-status-bar` flag.

## [3.0.0-alpha.51] - 2026-02-07

### Fixed

- Status bar not redrawn after resize: replaced background thread approach
  with main-loop deferred redraw to avoid interleaved escape sequences

## [3.0.0-alpha.50] - 2026-02-07

### Fixed

- Resize breaks child layout: DECSTBM resets cursor to (1,1) as side effect,
  now save/restore cursor around scroll region setup

## [3.0.0-alpha.49] - 2026-02-07

### Fixed

- Status bar disappears on terminal resize — child process redraw was
  overwriting it; added deferred redraw (150ms) after SIGWINCH

## [3.0.0-alpha.48] - 2026-02-07

### Fixed

- Cursor position on exit: prompt now appears at bottom of screen instead of
  overwriting content from top

## [3.0.0-alpha.47] - 2026-02-07

### Changed

- Status bar shows `voxtype X.Y.Z` right-aligned

## [3.0.0-alpha.46] - 2026-02-07

### Fixed

- InputFilter skipped trigger detection when `x_input` had `newline: true` —
  the guard now only skips if `x_input.submit` is already set, not for any
  truthy `x_input` value

## [3.0.0-alpha.45] - 2026-02-07

### Changed

- Status bar colors: dark gray background with green (connected), yellow
  (connecting), red (reconnecting) instead of reverse video. Replaced 🎤
  emoji with ● / ○ for better Linux terminal compatibility.

## [3.0.0-alpha.44] - 2026-02-07

### Added

- Status bar in `voxtype agent`: persistent last-row indicator showing
  connection state (connecting/connected/reconnecting) using DECSTBM scroll
  region. Subprocess sees 1 row less; status bar survives clear-screen and
  repositions on terminal resize.

## [3.0.0-alpha.43] - 2026-02-07

### Added

- Health check before subprocess fork in `voxtype agent`: verifies server
  is reachable before starting the command (prevents silent SSE failures)

## [3.0.0-alpha.42] - 2026-02-07

### Fixed

- `voxtype agent --server URL` ignored when placed after agent_id
  (allow_interspersed_args=False caused --server to leak into command)

## [3.0.0-alpha.41] - 2026-02-07

### Fixed

- Panel layout broken with long device names — shorten "MLX (Apple Silicon)" → "MLX",
  "GPU (CUDA)" → "CUDA" to fit `name_width=28`

## [3.0.0-alpha.40] - 2026-02-07

### Changed

- Further test speedup: polling in `test_engine.py` (0.32s → 0.11s per test),
  replace remaining `time.sleep(0.2)` in `test_local_receiver.py`

### Fixed

- mypy `no-redef` error: `pid` variable name conflict in `engine_start()`

## [3.0.0-alpha.39] - 2026-02-07

### Changed

- Replace `time.sleep()` with polling in test suite (2x speedup: 17.8s → 8s)
- Add readable named helpers: `_wait_for_calls()`, `_wait_queue_empty()`, `_drain()`

## [3.0.0-alpha.38] - 2026-02-07

### Fixed

- mypy errors in `cli.py`: `ResourceTracker._pid` accessed via `getattr()`,
  replaced lambda-tuple with proper `_force_exit()` function

## [3.0.0-alpha.37] - 2026-02-07

### Added

- Regression tests for panel state/device display (`test_panel.py`)
- Regression tests for hardware auto-detection (`test_hardware.py`)
- Tests for message factory functions (`test_messages.py`)
- Tests for model cache path resolution (`test_model_cache.py`)
- Total: 45 new tests (326 → 371), all run in <0.3s

## [3.0.0-alpha.36] - 2026-02-07

### Fixed

- Panel always showed "IDLE" — was reading state from `platform.stt.state` (doesn't
  exist) instead of `platform.state`

## [3.0.0-alpha.35] - 2026-02-07

### Changed

- `/status` endpoint now exposes OpenVIP spec fields (`state`, `connected_agents`,
  `uptime_seconds`) at the top level alongside `protocol_version`
- Implementation-specific details remain in `platform` object (backward-compatible)

## [3.0.0-alpha.34] - 2026-02-07

### Fixed

- **macOS regression**: MLX device not set in config during auto-detection, causing
  panel to show "on CPU" instead of "MLX (Apple Silicon)" after v3.0.0a30 panel fix
- Panel device display no longer falls back to platform heuristic — uses explicit
  device mapping including `mlx`

## [3.0.0-alpha.33] - 2026-02-07

### Changed

- HTTP endpoint `/tts` renamed to `/speech` (OpenVIP protocol alignment)

## [3.0.0-alpha.32] - 2026-02-07

### Fixed

- **Slow model loading**: cached models no longer contact HuggingFace on startup —
  uses local snapshot path directly, saving ~25s on each start
- **Engine crash on startup**: `headless` parameter leaked through `**kwargs` to
  `ctranslate2.Whisper()` which doesn't accept it — caused silent init failure
- Status panel showed "on CPU" even when CUDA was active — panel hardcoded
  device instead of reading it from `/status` endpoint
- Verbose mode now prints full traceback on init errors (was silently exiting)

### Added

- `/status` endpoint now includes `stt.device` field (cpu/cuda)
- `voxtype engine start --verbose` flag: shows debug logs in plain text instead of Live panel
  - Enables Python DEBUG logging to stderr
  - Polls /status and prints loading progress as text
  - Essential for diagnosing loading issues

### Fixed

- GPU not detected: `device=auto` now uses `nvidia-smi` to detect GPU when CUDA Python
  libs are missing, and prints install instructions instead of silently falling back to CPU
- When `nvidia-smi` is not installed, informs user that GPU detection is unavailable

### Changed

- Moved hardware acceleration detection from `cli.py` to `utils/hardware.py`
  (`auto_detect_acceleration()`), keeping CLI logic clean
- Added debug logging to engine model loading (STT, VAD phases)

## [3.0.0-alpha.27] - 2026-02-06

### Added

- `[client]` config section with `url` field for default engine URL in `voxtype agent`
- `[server]` section shown in config template with `host`/`port` comments
- `voxtype agent --server` flag now reads default from config when not specified

## [3.0.0-alpha.26] - 2026-02-06

### Changed - Align with OpenVIP v1.0 protocol

- Message type `message` → `transcription`, `tts` → `speech`
- Field `source` → `origin` in message factory
- Extension fields: `x_submit`/`x_visual_newline` → unified `x_input` standard extension
  - `x_input.submit` (was `x_submit.enter`), `x_input.newline` (was `x_visual_newline`)
- `partial` is now a core boolean field on transcription messages (was internal type)
- `/status` endpoint: protocol-level fields (`protocol_version`, `connected_agents`)
  at top level, implementation details under `platform` object
- Renamed classes: `SubmitFilter` → `InputFilter`, `SubmitExecutor` → `InputExecutor`
- StatusPanel reads from new `platform`-nested status structure
- All tests updated for new naming

### Removed

- Debug files: `error_output.txt`, `test_sanitization.py`

## [3.0.0-alpha.25] - 2026-02-06

### Fixed

- HTTP server now starts in all modes (keyboard and agents). Previously it
  only started in agent mode, causing StatusPanel to show "Connecting to
  engine..." indefinitely in keyboard mode.

## [3.0.0-alpha.24] - 2026-02-06

### Changed - Remove dead code + reorganize files (Step 6)

- Delete old `executors/` package (dead code from previous attempt: base.py,
  terminal.py, llm_agent.py — no external imports)
- Move filters into `pipeline/filters/` subdirectory:
  `submit_filter.py`, `agent_filter.py` → `pipeline/filters/`
- Pipeline structure now: `pipeline/{base,filters/,executors/}`
- Public API unchanged: `from voxtype.pipeline import AgentFilter, SubmitFilter`

## [3.0.0-alpha.23] - 2026-02-06

### Added - SubmitExecutor (Step 4)

- `SubmitExecutor` in `pipeline/executors/submit.py` — handles x_submit
  by calling write_fn with text and enter flag, consumes the message
- Available for agent-side pipeline integration (mux.py conversion
  already handles structured x_submit from Step 2)

## [3.0.0-alpha.22] - 2026-02-06

### Added - Engine-side executor pipeline (Step 3)

- `AgentSwitchExecutor` in `pipeline/executors/agent_switch.py` — handles
  x_agent_switch by calling the engine's switch function, consumes the message
- `Pipeline.process_many()` — convenience method for executor pipeline input
- Executor pipeline runs after filter pipeline in engine's `_inject_text()`
- Removed inline agent switch handling from engine (was only checking first
  message — now correctly handles switch in any position)

## [3.0.0-alpha.21] - 2026-02-06

### Changed - Structured extension fields (Step 2)

- `x_submit` is now a structured object: `{enter: true, trigger: "...", confidence: 0.99}`
  instead of flat `x_submit=True` + `x_submit_trigger` + `x_submit_confidence`
- `x_agent_switch` is now a structured object: `{target: "agent_id", confidence: 0.85}`
  instead of flat `x_agent_switch="agent_id"`
- Filters use `derive_message()` for ID triad (id, trace_id, parent_id)
- `derive_message()` handles messages without `id` field gracefully
- Updated all consumers: engine, agent mux, local receiver
- `create_message()` sets structured `x_submit` when `submit=True`

## [3.0.0-alpha.20] - 2026-02-06

### Changed - Pipeline foundation (Step 1)

- Rewrite `pipeline/base.py`: PipelineAction enum, PipelineResult dataclass with
  `passed()`, `augmented()`, `consumed()` factory methods
- Add `Executor` protocol (structural typing) with `name`, `field`, `process()`
- Add `Filter` protocol with `name`, `process()`
- Add `derive_message()` helper for ID triad (id, trace_id, parent_id)
- Rename Pipeline internals: `add_filter` → `add_step`, `filter_names` → `step_names`
- Rename across codebase: `FilterAction` → `PipelineAction`, `FilterResult` → `PipelineResult`

## [3.0.0-alpha.19] - 2026-02-06

### Fixed - "Last" text never shown in StatusPanel

- Engine `/status` endpoint returned hardcoded empty `last_text`
- Track last transcribed text in engine and include in HTTP status response

## [3.0.0-alpha.18] - 2026-02-06

### Fixed - Session stats not displayed on exit

- Display session stats BEFORE engine shutdown (stats were captured but
  never printed because the 3s force_exit timer killed the process first)
- Reduce HTTP server shutdown timeout from 5.0s to 0.5s (daemon thread)
- Reduce partial worker shutdown timeout from 1.0s to 0.3s (daemon thread)
- Remove unnecessary `gc.collect()` from shutdown path

## [3.0.0-alpha.17] - 2026-02-05

### Changed - Lite install mode (default)

- `./install.sh` now defaults to lite mode: only reinstalls voxtype package,
  leaves all dependencies untouched (MLX, ONNX, etc.)
- `./install.sh full` for full install (previous behavior)
- Dev mode lite: `uv pip install --no-deps --reinstall -e .`
- Non-dev mode lite: `uv tool install --reinstall-package voxtype`
- Falls back to full install if .venv doesn't exist yet

## [3.0.0-alpha.16] - 2026-02-05

### Fixed - Use historical load times for progress estimation

- Use `get_model_load_time()` / `save_model_load_time()` from stats system
  to persist cold load times and use them as progress bar estimates
- Only cold loads (≥50% of previous) are saved; warm loads are ignored
- First run uses 25s fallback, subsequent runs use actual historical time
- Fix race condition: set `start_time` before `status = "loading"`

## [3.0.0-alpha.15] - 2026-02-05

### Fixed - VAD loading progress stuck at "ETA 0s"

- Fix race condition: set `start_time` before `status = "loading"` to prevent
  `elapsed = time.time() - 0` when panel polls between the two assignments
- Increase VAD estimated time from 3s to 25s (first load can take 25s+)
- Increase STT estimated time from 20s to 25s for consistency

## [3.0.0-alpha.14] - 2026-02-05

### Fixed - Clean shutdown with resource_tracker kill

- Use `os._exit(0)` after killing resource_tracker to prevent Python from
  relaunching it during cleanup (was causing "process died unexpectedly" warning)
- Add 3-second force-exit timeout thread (same pattern as `listen` command)
  so Ctrl+C always exits promptly even if graceful shutdown stalls
- Extract `_kill_resource_tracker()` helper for reuse across signal/finally paths

## [3.0.0-alpha.13] - 2026-02-05

### Fixed - Semaphore leak warning in `engine start`

- Port resource_tracker kill fix to `engine start` foreground and daemon modes
- Kill `multiprocessing.resource_tracker` subprocess at shutdown to prevent
  "leaked semaphore objects" warnings from ONNX/MLX model processes
- Add force-exit (second Ctrl+C) handler with resource_tracker cleanup
- Fix pre-existing ruff error: `os` not imported in `engine_start()` function

## [3.0.0-alpha.12] - 2026-02-05

### Fixed - Loading progress bar not updating in real time

- Store `start_time` per model and compute `elapsed` dynamically in `/status`
- Progress bar now animates during model loading (was stuck at 0% before)
- ETA countdown updates every poll interval

## [3.0.0-alpha.11] - 2026-02-05

### Fixed - Ctrl+C not working in `engine start` foreground mode

- Signal handler now calls `panel.stop()` before `controller.request_shutdown()`
- Panel was stuck polling `/status` because HTTP server (daemon thread) was still alive
- `signal.signal(SIGINT)` suppressed `KeyboardInterrupt`, so `except` never triggered

## [3.0.0-alpha.10] - 2026-02-05

### Fixed - HTTP server starts before model loading

- Extracted `start_http_server()` from `start_runtime()` as a public method
- AppController now calls `start_http_server()` before `init_components()`
- StatusPanel can connect immediately and show loading progress
- Added loading progress tracking: `_loading_active`, `_loading_models` fields
- `init_components()` now tracks elapsed time for each model (STT, VAD)
- `/status` endpoint returns real loading state instead of hardcoded empty values
- `start_runtime()` still calls `start_http_server()` with no-op guard for backward compat

## [3.0.0-alpha.9] - 2026-02-04

### Changed - Config cleanup and dead code removal

- Updated `ServerConfig` docstring: clarifies server is always on in agent mode, `enabled` only for keyboard mode
- Updated `ServerConfig.enabled` description to reflect new semantics
- Updated `ServerConfig.port` description to mention OpenVIP
- Cleaned up stale socket/file agent references in docstrings:
  - `agent/base.py`: removed SocketAgent, WebhookAgent, WebSocketAgent from transport list
  - `core/engine.py`: removed SocketAgent, WebhookAgent from `_inject_text()` docstring
  - `output/local.py`: removed socket-based agent reference
  - `core/app.py`: removed stale "agent sockets" comment
- Deleted dead code:
  - `injection/socket.py` (SocketInjector — unused after socket agents removed)
  - `injection/file.py` (FileInjector — unused after file agents removed)
- Removed `TestFileInjectorRaceConditions` and `TestIntegrationRaceConditions` from test_race_conditions.py (referenced deleted FileInjector)

## [3.0.0-alpha.8] - 2026-02-04

### Added - Tests for new HTTP/SSE architecture

- Created `tests/test_http_server.py` — 17 tests for FastAPI OpenVIP server endpoints:
  - GET /status, POST /control, POST /tts endpoint tests
  - POST /agents/{id}/messages with connected/unconnected agents
  - `put_message()` thread-safe delivery tests
  - `connected_agents` property tests
  - Server lifecycle (start/stop/double-start) tests
- Created `tests/test_sse_agent.py` — 8 tests for SSEAgent:
  - Initialization, BaseAgent inheritance, repr
  - `send()` delegation to server, return values, message ordering
  - Thread safety: 5 concurrent threads × 50 messages
- Test count: 291 → 316 (+25 new tests)

## [3.0.0-alpha.7] - 2026-02-04

### Removed - Obsolete adapter, file/socket agents, registrars, watchers

- Deleted `adapters/openvip/adapter.py` (771 lines — old HTTP/SSE adapter)
- Deleted `adapters/openvip/__init__.py`, `adapters/openvip/messages.py` (re-export shim)
- Deleted `adapters/__init__.py` (empty package)
- Deleted `agent/file.py` (FileAgent — replaced by SSEAgent)
- Deleted `agent/socket.py` (SocketAgent — replaced by SSEAgent)
- Deleted `agent/registrar.py` (ManualAgent/AutoDiscovery registrars — agents self-register via SSE)
- Deleted `agent/watcher.py` (socket file discovery)
- Deleted `agent/monitor.py` (folder monitoring with watchdog/polling)
- Deleted `output/sse.py` (old stdlib HTTP SSE server — replaced by FastAPI)
- Deleted `tests/test_sse.py` (tests for old SSE server)
- Removed `watchdog` dependency from pyproject.toml
- Removed old SSE server usage from `core/app.py`
- Removed `discover_agents()` from `utils/platform.py`
- Updated `output/__init__.py` to remove SSEServer export
- Moved `get_pid_path` import in CLI from deleted adapter to `engine/engine.py`

## [3.0.0-alpha.6] - 2026-02-04

### Changed - Update CLI and agent mux to use SSE

- Rewrote agent mux IPC: replaced file/socket-based communication with SSE client
- Added `_read_from_sse()` — connects to engine HTTP server to receive OpenVIP messages
- Removed `_read_from_file()`, `_read_from_socket()`, and related helper functions
- Added `--server` option to `voxtype agent` command for specifying engine HTTP URL
- SSE connection automatically registers the agent with the engine (no file/socket setup)
- Exponential backoff retry on connection failure
- Removed `--agent` (manual agent list) and `--discovery` options from `voxtype listen`
- `--agents` now means "start HTTP server, agents connect via SSE"
- Updated help text and docstrings for SSE-based architecture

## [3.0.0-alpha.5] - 2026-02-04

### Changed - Simplify AppController, remove adapter dependency

- Removed `OpenVIPAdapter` dependency from `AppController` — engine now owns HTTP server lifecycle
- Simplified `start()`: creates engine, init components, start runtime (3 steps instead of 7)
- Simplified `stop()`: stops engine directly (no adapter intermediary)
- `run()` now delegates to `engine.run()` instead of `adapter.run()`
- `request_shutdown()` signals engine directly
- Removed `adapter` property
- `ControllerEvents` now only handles audio feedback and agent TTS (no adapter state sync)

## [3.0.0-alpha.4] - 2026-02-04

### Changed - Simplify create_engine(), remove registrar

- `create_engine()` now returns `VoxtypeEngine` directly (was tuple `(engine, registrar)`)
- Removed `manual_agents` and `discovery_method` parameters — agents self-register via SSE
- Updated all callers: `app/controller.py`, `core/app.py`, `daemon/server.py`, `engine/engine.py`
- Removed `_registrar` field from `AppController`, `DaemonServer`, `Engine`
- Simplified `VoxtypeApp.__init__()` — removed unused `manual_agents`, `discovery_method` params

## [3.0.0-alpha.3] - 2026-02-04

### Added - SSEAgent and HTTP server integration in engine

- Created `agent/sse.py` with `SSEAgent(BaseAgent)` for SSE message delivery
- Added HTTP server lifecycle to engine: starts in `start_runtime()`, stops in `stop()`
- Added `_register_sse_agent()` / `_unregister_sse_agent()` for SSE connection-based registration
- Added `_get_http_status()` for `/status` endpoint
- Added `_handle_tts_request()` for `/tts` endpoint
- Added `_handle_control()` for `/control` endpoint (stt.start/stop/toggle, output.set_agent, engine.shutdown, ping)
- HTTP server auto-starts when `agent_mode=True` or `config.server.enabled=True`

## [3.0.0-alpha.2] - 2026-02-04

### Changed - Move OpenVIP messages to core, rename to Interaction Protocol

- Created `core/messages.py` as canonical location for OpenVIP message factories
- Updated all imports: `core/engine.py`, `core/app.py`, `output/sse.py`, `injection/socket.py`, `engine/engine.py`, tests
- Made `adapters/openvip/messages.py` a backwards-compatibility re-export shim
- Renamed "Open Voice Input Protocol" to "Open Voice Interaction Protocol" in docstrings

## [3.0.0-alpha.1] - 2026-02-04

### Fixed - Stats not shown at exit

- Capture `engine.stats` before engine shutdown in `AppController.stop()`
- Pass stats snapshot to `_display_session_stats(stats)` instead of reading from nullified engine
- Stats are now correctly displayed on exit

## [2.109.0] - 2026-02-04

### Changed - SessionStats dataclass replaces individual stats properties

- Added `SessionStats` frozen dataclass with: `chars`, `words`, `count`, `audio_seconds`, `transcription_seconds`, `injection_seconds`, `start_time`
- Replaced 7 individual `stats_*` properties on VoxtypeEngine with single `engine.stats` property returning an immutable snapshot
- Updated `VoxtypeApp` and `AppController` to use `engine.stats` object

## [2.108.0] - 2026-02-04

### Added - TTS speak methods in VoxtypeEngine

- Added `speak_text(text)` and `speak_agent(agent_name)` to VoxtypeEngine
- Uses `play_audio(callable)` with OS TTS (`say` on macOS, `espeak`/`espeak-ng` on Linux)
- `pause_mic` determined by `headphones_mode` config (speaker mode mutes mic during TTS)
- TTS phrases configurable via `~/.config/voxtype/tts_phrases.json`
- `VoxtypeApp._speak_text()` and `_speak_agent()` now delegate to engine
- `AppController` now announces agent switches via `engine.speak_agent()` (was a TODO stub)
- Temporary OS-based TTS — will be replaced by TTS service in future version

## [2.107.1] - 2026-02-04

### Fixed - Sound files not included in installed package

- Added `artifacts = ["*.mp3"]` to `pyproject.toml` wheel config
- Bundled MP3 sound files (up-beep.mp3, down-beep.mp3) are now included in the wheel
- Previously `sounds/` directory was missing from `uv tool install` installations

## [2.107.0] - 2026-02-04

### Changed - Shared `play_audio()` with `pause_mic` parameter

- Added `play_audio(source, pause_mic, controller)` as the single entry point for all audio playback
- `pause_mic=True`: registers play_id, transitions to PLAYING (mic muted), resumes after playback
- `pause_mic=False`: fire-and-forget on background thread
- Caller decides `pause_mic` based on `headphones_mode` (high-level semantic)
- Replaced 40-line inline playback code in `app/controller.py` with single `play_audio()` call
- Replaced `_play_audio()` method in `core/app.py` — both `_speak_text` and `_play_feedback` now use shared function
- Removed unused imports (`PlayStartEvent`, `PlayCompleteEvent`, `Callable`, `threading`) from `core/app.py`

## [2.106.0] - 2026-02-04

### Changed - Submit filter: remove single-word triggers, add last-word-only notation

- Removed all single-word submit triggers from defaults (too many false positives)
- Kept only multi-word triggers with "ok" prefix (e.g., `["ok", "invia"]`, `["ok", "send"]`)
- Added last-word-only notation: `["vai."]` — trailing "." means trigger fires only if it's the very last word of the transcription
- Binary matching for last-word patterns: confidence 1.0 if last word matches, no match otherwise
- Added `["vai."]` as Italian last-word-only trigger

## [2.105.0] - 2026-02-04

### Changed - Rename TTS ID system to Play ID

- Renamed `TTSStartEvent` → `PlayStartEvent`, `TTSCompleteEvent` → `PlayCompleteEvent`
- Renamed `tts_id` → `play_id`, `get_next_tts_id()` → `get_next_play_id()`
- Renamed `tts_in_progress` → `play_in_progress`, `_desired_state_after_tts` → `_desired_state_after_play`
- The play ID counter now correctly reflects its purpose: managing ALL audio playback (beeps, TTS, custom sounds)
- Engine `_emit` now logs exceptions instead of silently swallowing them

## [2.104.0] - 2026-02-04

### Changed - Audio feedback with mic muting and configurable sounds

- Audio feedback now pauses listening (PLAYING state) during playback
- Uses the same play ID counter system: mic resumes only when ALL sounds finish
- Custom sound files configurable via `sound_start` / `sound_stop` in `[audio]` config
- Shared `_play_audio()` method used by both beep feedback and TTS speech
- Removed `sounds/` root directory from tracking (local staging only)

## [2.103.0] - 2026-02-04

### Changed - Clean audio feedback with bundled sound files

- Replaced generated sine wave beeps with bundled MP3 sound files
- Playback via `afplay` (macOS) / `paplay`/`aplay` (Linux) instead of sounddevice
- Eliminates crackling caused by sounddevice input/output conflict

## [2.102.1] - 2026-02-04

### Fixed - STT model name shown as "None" during loading

- Set `model_name` and `language` in state before model loading starts
- Panel now shows "large-v3-turbo on MLX" immediately instead of "None on MLX"
- Fixed in both Engine and OpenVIPAdapter code paths

## [2.102.0] - 2026-02-04

### Changed - VAD tuning and config template (nginx-style)

- `min_speech_ms` default lowered from 250ms to 150ms (faster trigger, Whisper filters noise)
- `pre_buffer_ms` default 640ms (was 320ms hardcoded)
- Default config template now shows ALL available options as comments (nginx-style)
- Users can see and uncomment advanced settings like `pre_buffer_ms`, `min_speech_ms`,
  `max_duration`, `translate`, `headphones_mode`

## [2.101.0] - 2026-02-04

### Added - Configurable VAD pre-buffer and min speech duration

New advanced audio settings to reduce speech onset clipping:
- `pre_buffer_ms` (default 640ms, was 320ms hardcoded) - audio captured before VAD triggers
- `min_speech_ms` (default 150ms) - minimum speech duration before VAD activates

## [2.100.10] - 2026-02-04

### Fixed - Submit trigger token slice off-by-one

`x_submit_trigger` was missing the last token due to `tokens[start:end]`
instead of `tokens[start:end+1]`. Now correctly shows full trigger
(e.g., `"ok invia"` instead of just `"ok"`).

## [2.100.9] - 2026-02-04

### Changed - Agent switch produces two messages

When saying "manda questo agent voxtype", the filter now produces TWO messages:
1. `{"text": "manda questo"}` - sent to CURRENT agent
2. `{"text": "", "x_agent_switch": "voxtype"}` - triggers switch, nothing written

This allows combining text + switch in one phrase. The switch-only message
(empty text) is not written to the agent file, consistent with submit behavior.

## [2.100.8] - 2026-02-04

### Fixed - Agent switch text not removed

When saying "agent voxtype", the trigger text was not being removed from the
message. This happened because Whisper sometimes splits words (e.g., "voxtype"
→ "Fox type"), and the old regex only handled single-word agent names.

Now removes everything from the trigger word to the end, consistent with
submit_filter behavior.

## [2.100.7] - 2026-02-04

### Fixed - Beep after every transcription

Audio feedback beep was playing on every TRANSCRIBING → LISTENING transition.
Now only plays on OFF → LISTENING (when user activates listening mode).

## [2.100.6] - 2026-02-04

### Added - Tests for message sending logic

Added 10 tests covering the empty text + submit handling logic:
- Empty/whitespace text without submit → not sent
- Empty/whitespace text WITH submit → sent (submit-only)
- Text with/without submit → sent
- Edge cases: missing keys, None values

## [2.100.5] - 2026-02-03

### Fixed - Submit-only messages not sent to agent

Empty text messages with `x_submit=true` were being skipped by the engine.
Now they are correctly sent to the agent, which handles them as submit-only
(just sends Enter without typing anything).

## [2.100.4] - 2026-02-03

### Fixed - JSONLLogger missing `_params` attribute

Fixed `AttributeError: 'JSONLLogger' object has no attribute '_params'` when
logging injections with verbose mode check.

## [2.100.3] - 2026-02-03

### Fixed - FileAgent reliability

FileAgent.send() now uses low-level I/O for reliability:
- `os.open()` with `O_APPEND | O_CREAT` (atomic append)
- `os.fsync()` to force data to disk
- Retry up to 3 times on failure with 100ms delay
- Better logging for debugging (warnings on failure)

### Changed - Verbose logging configurable

Logging now respects `--verbose` flag:
- With `--verbose`: shows actual text in logs
- Without: shows only metadata (chars, words, duration)
- Submit trigger is ALWAYS shown (useful for debugging)

## [2.100.2] - 2026-02-03

### Changed - Verbose logging by default

Logs now show actual text for debugging:

```
23:30:32 INFO  transcription        6240ms "ciao come stai oggi"
23:30:32 INFO  injection            via agent:voxtype "ciao come stai" [SUBMIT: "submit" 95%]
```

- `voxtype log engine -f` now shows transcription text
- Shows submit trigger word and confidence when detected
- Privacy mode can be re-added later if needed

## [2.100.1] - 2026-02-03

### Changed - File-based agent lifecycle

Agent files now use `.idle` extension when inactive (preserves history):

- **Agent starts**: renames `agent.jsonl.idle` → `agent.jsonl`
- **Agent exits**: renames `agent.jsonl` → `agent.jsonl.idle`
- **Engine/monitor**: only sees `.jsonl` files (ignores `.idle`)

Benefits:
- Session history preserved across restarts
- No file deletion needed
- Clean state management via extension

## [2.100.0] - 2026-02-03

### Fixed

**Socket persistent connection:**
- Bug: socket opened/closed for EVERY message → backlog overflow when speaking fast
- Fix: now uses persistent connection (connect once, send many messages)

**Submit trigger cleanup:**
- Bug: only trigger word was removed, leaving trailing text
- Fix: removes trigger word AND everything after it
- Example: "blabla submit della frase" → "blabla" (not "blabla della frase")

### Added

- Submit trigger logging: `x_submit_trigger` and `x_submit_confidence` in injection logs
- `voxtype log engine -f | grep submit_trigger` to debug false triggers
- `SocketAgent.connect()` and `SocketAgent.disconnect()` for persistent connections

## [2.99.0] - 2026-02-03

### Changed - File-based IPC (replacing sockets)

Switched from Unix socket to file-based IPC for engine→agent communication.
This fixes message loss issues that were occurring with socket-based transport.

- **FileAgent**: New agent that writes OpenVIP messages to JSONL files
- **Agent files**: Now stored in `~/.local/share/voxtype/agents/{agent_id}.jsonl`
- **Mux reader**: Uses unbuffered file I/O with tail-f style polling
- **Socket code**: Kept but fixed with persistent connection

### Added

- `_read_from_file()` function in mux.py for reliable file-based message reading
- `FileAgent` class in `agent/file.py`
- `get_agent_dir()` function in monitor.py

## [2.98.3] - 2026-02-03

### Added

- `voxtype log engine` command to view engine logs
- Engine now logs to `~/.local/share/voxtype/logs/engine.jsonl`
- Use `--verbose` with `engine start` to see full text in logs

### Fixed

- Engine was missing JSONLLogger, injections were not being logged

## [2.98.1] - 2026-02-03

### Added

- Session stats display in AppController (`_display_session_stats`)

### Note

- `core/app.py` (VoxtypeApp) kept as reference only - use `engine start` instead

## [2.98.0] - 2026-02-03

### Added - AppController architecture

New clean separation between Engine (atomic operations) and App (stateful logic):

- **`AppController`**: Central coordinator for foreground mode
  - Creates and manages Engine, Adapter, KeyboardBindingManager
  - Exposes app commands: `toggle_listening()`, `next_agent()`, `prev_agent()`
  - Used by both CLI and Tray (same code)

- **`KeyboardBindingManager`**: Handles all input bindings
  - Hotkeys (ScrollLock → toggle)
  - Keyboard shortcuts (Ctrl+Alt+→ → next_agent)
  - Device profiles (presenter buttons)

- **Architecture documentation**: `docs/specs/app-controller-architecture.md`

### Changed

- `engine start` now uses `AppController` instead of inline code
- `InputManager` accepts generic `CommandExecutor` protocol (not just `AppCommands`)
- Removed `_init_engine_and_adapter()` helper (logic moved to AppController)

## [2.97.1] - 2026-02-03

### Fixed - SubmitFilter false positives (#35)

- Remove single-word triggers that are too common:
  - Italian: "fatto", "adesso"
  - English: "go"
- Keep only explicit submit commands like "invia", "manda", "send", "submit"
- Multi-word triggers like "ok invia", "go ahead" still work

## [2.97.0] - 2026-02-03

### Added - COMMON init and daemon mode

- **`_init_engine_and_adapter()`**: Extracted shared initialization logic
  - Used by both foreground and daemon modes
  - Parameters: `mode` ("foreground"/"daemon"), `start_listening` (True/False)
- **Daemon mode implemented**: `voxtype engine start -d`
  - Headless operation, no UI
  - `start_listening=False` (privacy-aware default)
  - Waits for trigger via HTTP/socket API
  - Shows HTTP endpoint URL on startup

### Changed

- Foreground mode now uses shared `_init_engine_and_adapter()` function
- Cleaner separation between COMMON and mode-specific code

## [2.96.2] - 2026-02-03

### Fixed - Mypy type errors

- Fix `LoadingState | None` type error in `engine/engine.py` (null check before access)
- Convert `EngineEvents` from Protocol to base class with no-op implementations
- Removes the need for subclasses to implement all methods

## [2.96.1] - 2026-02-03

### Fixed - Skip empty messages after agent switch

- Don't send empty messages (e.g., when "Agent VoxType" is the entire phrase)
- Prevents unwanted newline when agent switch command is the only content

## [2.96.0] - 2026-02-03

### Added - Adapter event handling

- **last_text**: Panel now shows last transcribed text
- **hotkey.bound**: Auto-binds when engine starts with hotkey enabled
- **Audio feedback**: Beep on state change (LISTENING on/off), respects config
- `AdapterEvents` handles: `on_transcription`, `on_state_change`, `on_vad_loading`
- `hotkey_enabled=True` in engine creation (was False)

## [2.95.0] - 2026-02-03

### Changed - VoxtypeEngine lifecycle refactoring

- **`init_components(headless=False)`**: Load models (STT, VAD, audio, hotkey)
- **`start_runtime(start_listening=False)`**: Start controller, audio streaming
  - Default `start_listening=False` (privacy-aware, conservative)
- **`run()`**: Blocking loop for standalone use
- **`start()`**: Convenience method (init_components + start_runtime + run)
- Renamed `_init_vad_components` → `init_components` (public API)
- Adapter no longer accesses engine internals

## [2.94.0] - 2026-02-03

### Changed - Unified StatusPanel design

- Models (STT, VAD, TTS) always visible at top of panel
- Progress bars show loading progress with magenta color
- After loading: model lines show ✓ and load time
- Status info appears below models when ready
- Proper VAD loading tracking via `on_vad_loading` event
- Cleaner visual hierarchy

## [2.93.3] - 2026-02-03

### Fixed - Clean exit on Ctrl+C

- StatusPanel exits immediately when engine shuts down (no "Connecting..." message)

## [2.93.2] - 2026-02-03

### Fixed - StatusPanel improvements

- **Loading progress**: Progress bars now animate properly (track `elapsed` time)
- **IDLE → LISTENING**: Fix race condition, state set in `initialize_engine()`
- **Server URL**: Panel now shows HTTP server URL for easy reference

## [2.93.1] - 2026-02-03

### Removed - core/openvip.py backwards compatibility

- **Deleted** `core/openvip.py` - no need for backwards compatibility in development
- Updated all imports to use `voxtype.adapters.openvip.messages` directly

## [2.93.0] - 2026-02-03

### Changed - OpenVIP adapter architecture

- **adapters/openvip/**: New adapter package
  - `adapter.py`: `OpenVIPAdapter` wraps VoxtypeEngine and exposes OpenVIP protocol (HTTP + Unix socket)
  - `messages.py`: OpenVIP message creation functions (moved from core/openvip.py)
- **cli.py**: `engine start` uses OpenVIPAdapter instead of direct engine wrapper
- **Architecture**: VoxtypeEngine (pure Python) + OpenVIPAdapter (protocol translation)

## [2.92.2] - 2026-02-03

### Fixed - Agent discovery in Engine

- **engine/engine.py**: Call `registrar.start()` after models loaded
  - Agent discovery now works in `voxtype engine start --agents`
  - Agents will appear in panel once discovered

## [2.92.1] - 2026-02-03

### Fixed - Graceful shutdown on Ctrl+C

- **ui/panel.py**: Handle connection errors gracefully
  - Catch `ConnectionResetError` and `OSError` in `_fetch_status()`
  - Track connection state to detect engine shutdown
  - Exit cleanly after 3 consecutive failures (engine stopped)
  - Show "Connecting..." instead of error during startup

## [2.92.0] - 2026-02-03

### Added - StatusPanel with HTTP polling (Phase 5)

- **ui/panel.py**: New `StatusPanel` class that polls `/status`
  - During loading: shows progress bars for each model (stt, vad)
  - After loading: shows normal status panel (state, last text, agents)
  - Same visual style as `LiveStatusPanel`
  - Poll interval: 300ms
- **cli.py**: `engine start` now uses `StatusPanel`
  - Engine init runs in background thread
  - Engine main loop runs in background thread
  - StatusPanel runs in main thread (handles Ctrl+C)
  - Clean shutdown on interrupt

## [2.91.6] - 2026-02-03

### Changed - Remove progress bars from engine start (defer to Panel)

- **cli.py**: Simplified `engine start` foreground mode
  - Removed Rich Progress bars (will be in Panel, Phase 5)
  - Simple spinner "Loading models..." during initialization
  - Progress data still available via `/status` for polling
- **Architecture alignment**: Engine is headless, Panel handles all UI

## [2.91.5] - 2026-02-03

### Fixed - Progress bar reaches 100% for all models

- **cli.py**: Final poll after init loop to catch last model completion
  - Refactored to `update_progress_from_status()` helper
  - Removed `loading.active` check - process models regardless
  - Final poll ensures all models show ✓ at 100%

## [2.91.4] - 2026-02-03

### Fixed - CLI progress bar updates in-place

- **cli.py**: Use Rich Progress instead of printing lines
  - Progress bars now update on the same line (proper UX)
  - Shows spinner + bar + percentage + ETA for each model
  - Completed models show green checkmark with load time
  - Poll interval reduced to 200ms for smoother updates

## [2.91.3] - 2026-02-03

### Changed - Headless Engine (no internal progress bars)

- **Engine is now headless**: No Rich progress bars during model loading
  - All console output suppressed when running via `voxtype engine start`
  - Progress visualization is responsibility of CLI/UI polling `/status`
  - Stats (load times) are still tracked for historical estimates
- **headless parameter** propagated through loading chain:
  - `load_with_indicator(headless=True)` skips Rich console output
  - `SileroVAD._load_model(headless=True)` skips VAD progress bar
  - `MLXWhisperEngine.load_model(headless=True)` skips STT progress bar
  - `AudioManager.initialize(headless=True)` passed to VAD
  - `VoxtypeEngine._init_vad_components(headless=True)` passed from Engine
- **Architecture**: Clean separation between Engine (data/state) and UI (rendering)

## [2.91.2] - 2026-02-03

### Fixed - Actually load models in engine init

- **engine.py**: Call `_init_vad_components()` after `create_engine()`
  - `create_engine()` only creates the engine, doesn't load models
  - Models are loaded in `_init_vad_components()` which triggers events
  - Now STT→done and VAD→done states are correctly updated

## [2.91.1] - 2026-02-03

### Fixed - Signal handlers in main thread

- **cli.py**: Register signal handlers in main thread, not init thread
- **engine.py**: Add `setup_signals` parameter to `_do_initialize()`

## [2.91.0] - 2026-02-03

### Added - Polling-based loading progress in CLI

- **cli.py**: `engine start` now polls `/status` during model loading
  - Shows real-time progress: `Loading stt... 63% (17.0s / ~27s, ETA: 10s)`
  - Shows completion: `✓ stt loaded in 21.1s`
  - Runs initialization in thread, polls HTTP endpoint
- **Testing**: Can verify `/status` returns correct loading progress

## [2.90.0] - 2026-02-03

### Changed - Engine Architecture: Separate initialize/run

- **engine/engine.py**: Split lifecycle into `initialize()` and `run()`
  - `initialize()` - starts HTTP server, loads models (non-blocking after server starts)
  - `run(start_listening)` - main loop, optionally starts listening
  - `start()` - convenience method (calls both, backward compatible)
- **engine/state.py**: Enhanced `LoadingState` for on-the-fly progress
  - `ModelLoadingProgress` - tracks each model's loading status
  - Progress calculated as `elapsed / historical_time` when `/status` polled
  - HTTP server responds during model loading (ThreadingHTTPServer)
- **Purpose**: Enable UI panel to poll `/status` during loading and show progress

## [2.89.0] - 2026-02-03

### Added - Engine CLI Commands

- **cli.py**: New `voxtype engine` command group for new architecture
  - `voxtype engine start --keyboard` - foreground mode, listening immediately
  - `voxtype engine start --agents` - agent mode, listening immediately
  - `voxtype engine start -d --agents` - daemon mode, models preloaded but IDLE
  - `voxtype engine stop` - stop running engine via PID
  - `voxtype engine status` - show engine status (supports `--json`)
- **engine/__init__.py**: Export `get_pid_path`, `get_socket_path` utilities
- **Strategy**: Incremental migration from `core/` to `engine/`
  - `voxtype listen` continues to work (uses `core/`)
  - `voxtype engine start` uses new `engine/` architecture
  - Both can be tested in parallel before final migration

## [2.88.0] - 2026-02-03

### Simplified - Exact Match for Trigger Words

- **agent_filter.py**: Removed fuzzy matching for trigger words
  - Trigger "agent" now uses exact match only
  - Fuzzy/phonetic matching only for agent IDs (where it's needed)
  - Removed language-aware matching strategy (unnecessary complexity)
  - Code is simpler and easier to understand
- **Rationale**: "agent" is a common word Whisper recognizes reliably
  - Fuzzy matching on triggers added complexity without real benefit
  - Agent IDs can be arbitrary names → fuzzy matching valuable there

## [2.87.1] - 2026-02-03

### Changed - Default AgentFilter Triggers

- **config.py**: Default triggers now English-only: `["agent"]`
  - Removed "agente" from defaults (users add their language triggers)
  - Consistent with open-source approach: English defaults, users customize
  - If we include Italian, we'd need French, German, Spanish, etc.
- **tests**: Updated to pass triggers explicitly when testing non-English

## [2.87.0] - 2026-02-03

### Changed - Language-Aware Trigger Matching

- **agent_filter.py**: Use message language to select matching strategy
  - **English**: phonetic + edit distance (metaphone works well)
  - **Other languages**: edit distance only (metaphone unreliable)
  - Uses `language` field from Whisper transcription
- **tests**: Added language-specific trigger tests

## [2.86.0] - 2026-02-03

### Added - Fuzzy Matching for Trigger Words

- **agent_filter.py**: Apply fuzzy matching to trigger words
  - Handles STT errors like "adziente" → "agente", "aziente" → "agente"
  - Uses edit distance only (metaphone doesn't work well for non-English)
  - 60% character similarity threshold for triggers
- **tests**: Added fuzzy trigger tests

## [2.85.1] - 2026-02-03

### Fixed - Pipeline Initialization Order

- **engine.py**: Move `_agent_order` initialization before `_create_pipeline()`
  - Fixed `AttributeError: 'VoxtypeEngine' object has no attribute '_agent_order'`
  - AgentFilter now correctly gets empty list on startup (updates via events)

## [2.85.0] - 2026-02-03

### Changed - Event Sourcing Semantics

Changed event bus semantics from snapshot-based to proper event sourcing:

- **Before**: `agents.changed` with full list `["a", "b", "c"]`
- **After**: `agent.registered` / `agent.unregistered` with single `agent_id`

This is the correct event-driven architecture:
- Each event is atomic and immutable
- Events shouldn't be lost; if they are, it's an architectural problem
- Subscribers maintain their own state from event stream

**Engine** now publishes:
- `agent.registered` with `agent_id` on register
- `agent.unregistered` with `agent_id` on unregister

**AgentFilter** now subscribes to both events and maintains its agent list.

## [2.84.0] - 2026-02-03

### Added - AgentFilter Pipeline Integration

- **engine.py**: Integrates AgentFilter with engine and event bus
  - Publishes `agents.changed` event on register/unregister
  - Creates AgentFilter from config if `pipeline.agent_filter.enabled`
  - Handles `x_agent_switch` field: switches to target agent
- **config.py**: Added `AgentFilterConfig`
  - `enabled`: false by default (opt-in)
  - `triggers`: ["agent", "agente"]
  - `match_threshold`: 0.5
- Added to `PipelineConfig.agent_filter`

### Usage

Enable in `~/.config/voxtype/config.toml`:

```toml
[pipeline.agent_filter]
enabled = true
```

Then say "agent voxtype" or "agente claude" to switch agents.

## [2.83.0] - 2026-02-03

### Added - Internal Event Bus

- **events/bus.py**: NEW - Thread-safe internal event bus
  - Publish/subscribe pattern for decoupled component communication
  - Global singleton `bus` instance for app-wide usage
  - Thread-safe with `threading.Lock`
  - `bus.subscribe(event, callback)` / `bus.publish(event, **data)`
  - `bus.reset()` for test isolation
  - Custom implementation (~40 lines) - no external dependencies
- **events/__init__.py**: NEW - Exports `EventBus`, `bus`
- **pipeline/agent_filter.py**: Now subscribes to "agents.changed" event
  - Dynamic agent list updates without manual refresh
  - `subscribe_to_events=True` by default
- **tests/test_event_bus.py**: NEW - 14 tests for EventBus
  - Basic subscribe/publish/unsubscribe
  - Thread safety (concurrent publish/subscribe)
  - Error handling (callback exceptions don't stop others)
- **tests/test_pipeline.py**: Added 5 EventBus integration tests for AgentFilter

## [2.82.0] - 2026-02-03

### Added - Agent Filter with Phonetic Matching
- **pipeline/agent_filter.py**: NEW - Voice-controlled agent switching
  - Detects "agent <name>" or "agente <name>" at end of text
  - Uses **jellyfish** library for phonetic matching (Metaphone)
  - Combined scoring: 60% phonetic + 40% edit distance (Levenshtein)
  - Handles misheard names: "coder"/"quant" matches "koder"
  - Sets `x_agent_switch` field with matched agent ID
- **pyproject.toml**: Added `jellyfish>=1.0.0` dependency
  - Lightweight (~100KB), C-based, zero dependencies
- **pipeline/__init__.py**: Exports `AgentFilter`
- **tests/test_pipeline.py**: 22 new tests for AgentFilter
  - Phonetic matching functions
  - Detection and fuzzy matching
  - Pipeline integration

## [2.81.0] - 2026-02-03

### Added - Italian "in via" Trigger
- **submit_filter.py**: Added "in via" as submit trigger for Italian
  - Whisper often transcribes "invia" as "in via"
  - Added both `["in", "via"]` and `["ok", "in", "via"]` patterns
- **test_pipeline.py**: Added test for "in via" trigger

### Fixed - CI Pipeline
- **ci.yml**: Fixed Linux runners by using `uv venv` + `uv pip install`
  - Previous `uv sync` approach had issues with dev dependencies
  - macOS still uses `uv sync` (was working)

## [2.80.0] - 2026-02-03

### Fixed - CI Pipeline Mypy Errors
- **tray/app.py**: Fixed hotkey listener creation
  - Use `PynputHotkeyListener` directly instead of non-existent `create_listener`
  - Fix config access: `config.hotkey.key` instead of `config.keyboard.hotkey`
- **engine/server.py**: Fixed Queue type annotation for SSE events
  - `Queue[dict[Any, Any] | None]` to allow None sentinel
- **engine/control.py**: Fixed response dict type annotation
  - `dict[str, Any]` to allow nested error dict
- **engine/engine.py**: Fixed STTEventHandler abstract class
  - Added all missing method stubs (on_engine_ready, on_recording_start, etc.)

## [2.79.0] - 2026-02-03

### Added - Idiomatic Python Logging
- **logging/setup.py**: NEW - Idiomatic Python structured logging
  - Uses standard `logging.getLogger(__name__)` pattern (thread-safe, global)
  - `python-json-logger` for JSON formatting
  - `VoxtypeJsonFormatter`: Adds ts, level, event, logger fields
  - `setup_logging()`: Configure once at app startup
  - `shutdown_logging()`: Clean shutdown with session_end event
- **logging/__init__.py**: Exports new idiomatic API alongside legacy
  - New: `setup_logging`, `shutdown_logging`, `DEFAULT_LOG_DIR`, `get_default_log_path`
  - Legacy (deprecated): `JSONLLogger`, `LogLevel`
- **submit_filter.py**: Migrated to idiomatic logging
  - Uses `logger = logging.getLogger(__name__)`
  - Logs `submit_trigger` event with pattern, matched_tokens, confidence
- **tests/test_logging.py**: NEW - Tests for logging setup
  - Tests for `VoxtypeJsonFormatter`, `setup_logging`, `shutdown_logging`
  - Tests module-level logger pattern

## [2.78.1] - 2026-02-03

### Added - Submit Filter Logging
- **submit_filter.py**: Logs INFO when trigger is detected
  - Shows: pattern matched, tokens, confidence, text snippet
  - Helps debug false positive triggers

## [2.78.0] - 2026-02-03

### Fixed - Pipeline Now Receives Language
- **openvip.py**: Added `language` parameter to `create_message()`
- **engine.py**: Passes configured STT language to messages
  - If `stt.language` is set (e.g., "it"), uses that
  - If "auto", defaults to "it" (temporary workaround)
- This enables language-based trigger detection in the pipeline

## [2.77.0] - 2026-02-03

### Added - Language-Based Trigger Words
- **submit_filter.py**: Trigger words now organized by language code
  - Triggers for detected message language + English (always)
  - Supports it, en, es, de, fr out of the box
  - Easy to add new languages without touching existing ones
- **config.py**: Updated trigger config structure
  - `triggers` is now a dict keyed by language code (e.g., `triggers.it`, `triggers.en`)
  - Each language has its own list of trigger patterns
- **Language detection**: Uses `language` field from Whisper transcription
  - Falls back to English if language unknown
  - Normalizes codes like "en-US" to "en"

## [2.76.0] - 2026-02-03

### Added - Pipeline Filter System
- **pipeline/**: New message processing pipeline with filter architecture
  - `pipeline/base.py`: Filter protocol, FilterAction, FilterResult, Pipeline classes
  - `pipeline/submit_filter.py`: Submit trigger detection filter
  - Messages flow through configurable filters before delivery to agents
- **SubmitFilter**: Detects trigger words at end of text for automatic submit
  - Trigger words: "ok invia", "submit", "send", "fatto", "manda", etc.
  - Position-weighted confidence: words closer to end have higher weight
  - Configurable threshold, decay rate, and max scan distance
  - Removes trigger words and sets `x_submit=true` on message
- **config.py**: New `[pipeline]` configuration section
  - `pipeline.enabled`: Enable/disable the pipeline (default: true)
  - `pipeline.submit_filter.*`: Configure submit filter behavior
- **engine.py**: Pipeline integration in `_inject_text()` method

## [2.75.1] - 2026-02-02

### Fixed - Session Log Formatting
- **cli.py**: Fixed `voxtype log session` output formatting
  - `session_start` now shows version and agent_id correctly
  - `session_end` shows exit code and keystroke count
  - `msg_read` and `msg_sent` now show message text (up to 80 chars)
  - Fixed timestamp parsing for session files (`timestamp` vs `ts` field)

## [2.75.0] - 2026-02-02

### Added - Session Log Tail Command
- **cli.py**: Added `voxtype log session <agent_id>` command
  - Shows the most recent session log for an agent
  - `-f` / `--follow` for live tail (like tail -f)
  - `-n` / `--lines` to specify number of lines
  - Automatically finds latest session file by agent ID

## [2.74.1] - 2026-02-02

### Fixed - Agent Verbose Flag Parsing
- **cli.py**: Fixed `--verbose` flag not working when placed after agent_id
  - `voxtype agent claude --verbose -- cmd` now works correctly
  - Flags after positional args were going to ctx.args due to allow_interspersed_args=False

## [2.74.0] - 2026-02-02

### Added - Verbose Mode for Agent
- **cli.py**: Added `--verbose` / `-v` flag to `voxtype agent` command
- **agent/mux.py**: When verbose, session log contains full text (not truncated to 50 chars)
  - Useful for debugging message loss between listen and agent
  - Compare `voxtype listen --verbose` output with `voxtype agent --verbose` session log

## [2.73.3] - 2026-02-02

### Fixed - Duplicate Agent Names Allowed
- **agent/mux.py**: Added `_is_socket_active()` check before starting agent
  - Verifies if socket has active listener before allowing registration
  - Returns error if agent with same ID is already running
  - Prevents multiple agents binding to same socket path

## [2.73.2] - 2026-02-02

### Fixed - Agent Messages Being Dropped (Race Conditions)
- **agent/socket.py**: SocketAgent now has retry logic and failure threshold
  - Retries up to 3 times with increasing timeouts (1s, 2s, 3s)
  - Only triggers deregistration after 3 consecutive failures
  - Single transient failure no longer removes agent permanently
- **core/engine.py**: Removed aggressive `is_alive()` checks during agent switching
  - Previously, switching agents would connect to socket to verify liveness
  - If receiver was busy, agent got unregistered even if alive
  - Now agent liveness is verified lazily on send()

## [2.73.1] - 2026-02-01

### Fixed - KeyboardAgent Not Starting with --keyboard Flag
- **core/app.py**: KeyboardAgent.start() was never called in VoxtypeApp
  - Now explicitly starts KeyboardAgent when not in agent mode
- **cli.py**: config.output.mode not updated from CLI flags
  - --keyboard now correctly sets config.output.mode = "keyboard"
  - Status panel now shows correct output mode

## [2.73.0] - 2026-01-31

### Added - New Engine Architecture (Phase 1)
- **engine/**: New unified engine package for v3.0.0 architecture
  - `engine/state.py`: EngineState dataclass with full status schema
  - `engine/control.py`: OpenVIP control command handlers
  - `engine/server.py`: HTTP + Unix socket transport layer
  - `engine/engine.py`: Main Engine class with foreground/daemon modes
- **State Schema**: Complete state exposed via `/status` endpoint
  - STT, TTS, Translation service states
  - Loading progress, output mode, hotkey binding
  - Engine metadata (version, pid, uptime)
- **OpenVIP Control**: All commands idempotent
  - `stt.start`, `stt.stop`, `tts.speak`, `tts.stop`
  - `output.set_mode`, `output.set_agent`
  - `hotkey.bind`, `hotkey.unbind`
  - `engine.shutdown`, `ping`
- **Dual Transport**: Same API on both transports
  - Unix socket: `~/.voxtype/engine.sock`
  - HTTP: port 9876 with SSE events
- **Metrics**: Session and lifetime metrics tracking

## [2.72.0] - 2026-01-30

### Added - Hotkey Support in Tray
- **tray/app.py**: Tray now registers global hotkey listener
  - Works on macOS (tray runs on main thread)
  - Pressing hotkey (e.g., CMD) toggles listening via daemon
  - Same tap detection as CLI (single tap = toggle)

## [2.71.0] - 2026-01-30

### Changed - Engine Manages KeyboardAgent Lifecycle
- **core/engine.py**: Engine now owns and manages KeyboardAgent lifecycle
  - KeyboardAgent is started/stopped automatically in engine.start()/stop()
  - No longer needs to be returned from create_engine or managed by app
  - Added `hotkey_enabled` parameter (default True)
- **daemon/server.py**: Disabled hotkey in daemon mode
  - macOS requires main thread for hotkey events, but daemon runs engine in background
  - Users toggle via tray menu instead

## [2.70.2] - 2026-01-30

### Fixed - Mypy Type Errors
- **core/engine.py**: Fixed type annotation for registrar variable
- **core/engine.py**: `create_engine()` now returns 3-tuple: (engine, registrar, keyboard_agent)
- **core/app.py**: Updated to unpack keyboard_agent from create_engine
- **daemon/server.py**: Updated to handle 3-tuple return

## [2.70.1] - 2026-01-30

### Fixed - Tray UI Blocking
- **tray/app.py**: Menu actions now run in background threads
  - "Start/Stop Listening" no longer freezes UI for seconds
  - Output mode changes also async
  - UI stays responsive, polling updates state

## [2.70.0] - 2026-01-30

### Fixed - Daemon State Synchronization
- **daemon/server.py**: Daemon now properly syncs state with engine
  - `on_state_change` callback now updates daemon state (was doing nothing!)
  - Hotkey toggles now correctly update daemon state
  - State changes from any source (hotkey, API, tray) now reflected correctly
- **tray/app.py**: Don't stop polling when stopping listening
  - Tray always polls to stay in sync with daemon

## [2.69.2] - 2026-01-30

### Fixed - Daemon Crash on Start Listening
- **core/engine.py**: Fixed `create_engine()` accessing non-existent `config.realtime`
  - `realtime` is a CLI parameter, not a config attribute
  - Now defaults to `False` when not specified

## [2.69.1] - 2026-01-30

### Fixed - Daemon Config Loading
- **daemon/server.py**: Load output mode from config at startup
  - Was showing "keyboard" instead of actual config value
  - Config is now loaded eagerly for correct status display

## [2.69.0] - 2026-01-30

### Refactored - Unified Engine Initialization
- **core/engine.py**: Added `create_engine()` factory function
  - Shared initialization logic for both daemon and CLI
  - Supports override parameters (agent_mode, realtime, manual_agents)
  - Ensures identical behavior between `voxtype listen` and daemon
- **core/app.py**: Now uses `create_engine()` instead of duplicated code
- **daemon/server.py**: Now uses `create_engine()` instead of duplicated code

## [2.68.0] - 2026-01-30

### Fixed - Daemon Agent Discovery
- **daemon/server.py**: Daemon was not discovering agents at all
  - Added `AutoDiscoveryRegistrar` to discover and register socket agents
  - Agents are now properly discovered when daemon starts in agent mode
- **tray/app.py**: Removed useless loading percentage (always 0%)
- **cli.py**: Enhanced `daemon status` to always show agent count for debugging

## [2.67.0] - 2026-01-30

### Fixed - Tray Sync and Command Mode Cleanup
- **tray/app.py**: Fixed tray not syncing with daemon state
  - Removed `processing_mode` parameter from `set_state()` (was causing silent errors)
  - Removed "Switch to Command Mode" menu item (command mode no longer exists)
  - Removed "(Transcription)" from status display
  - Added version display in tray menu (`voxtype vX.Y.Z`)
  - Added error logging for poll failures instead of silent ignore

## [2.66.0] - 2026-01-30

### Fixed - Config Set TOML Serialization
- **config.py**: Fixed `_format_toml_value()` to properly serialize lists and dicts to TOML
  - Lists of inline tables (like `keyboard.shortcuts`) now use correct TOML syntax
  - Was using Python `str()` which produced invalid syntax like `[{'key': 'value'}]`
  - Now outputs valid TOML: `[{ key = "value" }]`

## [2.65.0] - 2026-01-30

### Fixed - CLI Command Options Cleanup
- **cli.py**: Removed remaining `config.command` references that caused crash on startup
  - Removed CLI options: `--wake-word`, `--initial-mode`, `--no-commands`, `--ollama-model`
  - Removed LLM status display from `voxtype models list`
  - Removed `--llm` option from `voxtype models use`
  - Removed unused `_get_ollama_models()` function
  - Cleaned up logger parameters (removed `trigger_phrase`)

## [2.64.0] - 2026-01-30

### Fixed - Mypy Type Errors
- **stats.py**: Added `model_load_times` to `StatsData` TypedDict
- **watcher.py**: Fixed `Observer` type annotation, handle `bytes | str` paths
- **monitor.py**: Handle `bytes | str` paths from watchdog events
- **status.py**: Removed reference to deleted `config.command.mode`
- **keyboard.py**: Fixed `typing_delay` → `typing_delay_ms`
- **daemon/server.py**: Removed references to deleted `mode` property
- **app_commands.py**: Removed commands for deleted methods (`toggle-mode`, `repeat`)
- **app.py**: Added `on_engine_ready()` implementation, use `create_message()`
- **plugins/__init__.py**: Added type ignore for Protocol `issubclass()` checks

### Changed
- **CI workflow**: Now runs on all branches (not just main)

## [2.63.0] - 2026-01-30

### Changed - OpenVIP v1.0 Protocol Simplification
- **Message types simplified to 3**: `message`, `partial`, `status`
- **openvip.py**: New specific factories `create_message()`, `create_partial()`, `create_status()`
- **SSE server**: Updated to emit v1.0 compliant messages
  - `send_state_change()` now emits `status` type (was `state`)
  - `send_error()` now emits `status` with `status: "error"` (was separate `error` type)
  - State mapping: RECORDING→`recording`, TRANSCRIBING→`transcribing` (was both `listening`/`processing`)

### Removed
- **SSE methods**: `send_transcription()`, `send_transcription_result()`, `send_mode_change()`, `send_start()`, `send_end()`
- **Message types**: `state`, `error`, `start`, `end` (consolidated into `status`)

### Added
- **Vision document**: Updated `docs/notes/mental-model.md` with OpenVIP Platform vision
  - Three core services: STT, TTS, Translation
  - Service modes: enabled, on-demand, disabled
  - Services as protocol roles (Source, Sink, Pipeline Element)

## [2.62.0] - 2026-01-30

### Changed
- **Archive obsolete docs**: Moved LLM-related documentation to `docs/notes/archive/`
  - `llm-architecture.private.md` - LLM Processor design (not in v1.0)
  - `roadmap.private.md` - outdated roadmap

## [2.61.0] - 2026-01-30

### Removed - OpenVIP v1.0 Cleanup
- **LLM Processor**: Removed `src/voxtype/llm/` directory entirely
  - LLM-based command processing is out of scope for OpenVIP v1.0 core
  - Will be available as optional plugin in future
- **CommandConfig**: Removed `[command]` section from config
  - `command.mode` - no longer needed (no LLM vs transcription mode)
  - `command.wake_word` - removed
  - `command.ollama_model` - removed
  - `command.ollama_timeout` - removed
- **ProcessingMode**: Removed `ProcessingMode` enum from state machine
  - No more TRANSCRIPTION/COMMAND mode switching
  - Double-tap hotkey now switches agents instead of modes
- **Engine simplification**:
  - Removed `trigger_phrase`, `_llm_processor`, `_processing_mode`
  - Removed `_switch_processing_mode()`, `_repeat_last_injection()`
  - Removed `on_mode_change` callback
  - Hotwords now only from `stt.hotwords` config

### Changed
- **Engine docstring**: Now describes OpenVIP v1.0 protocol instead of "LLM-first architecture"
- **Double-tap hotkey**: Now cycles to next agent (was: switch transcription/command mode)

## [2.60.0-alpha] - 2026-01-29

### Changed
- **OpenVIP spec**: Removed duplicate internal spec, now points to official https://github.com/open-voice-input/spec
- **spec/README.md**: Documents voxtype-specific extensions (`x_submit`, `x_visual_newline`)

### Added
- **Service Layer**: New `voxtype.services` module with high-level APIs
  - `STTService`: Speech-to-text with daemon integration and local fallback
  - `TTSService`: Text-to-speech with daemon integration and local fallback
  - `ServiceRegistry`: Lazy-loaded registry for all services
- **Plugin System**: New `voxtype.plugins` module for extensibility
  - `Plugin` protocol and `BasePlugin` base class
  - Plugin discovery: built-in, entry points (`voxtype.plugins`), user plugins (`~/.config/voxtype/plugins/`)
  - CLI integration: plugins can add subcommands
- **Daemon STT Support**: New `stt.transcribe` action in daemon protocol
  - `STTRequest`/`STTResponse` message types
  - Daemon caches STT engine for fast repeated transcriptions
  - Client `send_stt_request()` method with base64 audio encoding

## [2.58.0] - 2026-01-29

### Changed
- **Config: `[server]` replaces `[sse]`**:
  - `server.enabled` - Enable HTTP/SSE server
  - `server.host` - Default `127.0.0.1` (localhost only for security, no auth yet)
  - `server.port` - Default `8765`

### Removed
- **CLI options**: `--daemon`/`-d`, `--sse`, `--sse-port`, `--webhook`
  - Server config now only via config file
  - For background mode, use `voxtype daemon start`
- **Config**: `[webhook]` section removed (will become an agent in future)

## [2.57.0] - 2026-01-29

### Changed
- **CLI: Explicit mode required**: `voxtype listen` now requires `--keyboard` or `--agents`
  - No more implicit mode from config (was confusing)
  - Clear error message with examples if mode not specified
  - Config `output.mode` is now only used by daemon
- **New flag**: `--keyboard` / `-K` for keyboard mode

### Removed
- **`-d` alias** from `--max-duration`

## [2.56.3] - 2026-01-29

### Fixed
- **HuggingFace progress bars**: Set `HF_HUB_DISABLE_PROGRESS_BARS=1` at CLI entry point
  - Single place: cli.py, before any imports
  - Removed redundant disable_progress_bars()/enable_progress_bars() from:
    - faster_whisper.py
    - qwen3.py
    - outetts.py
    - hf_download.py
  - Eliminates tqdm "Fetching X files" output during model loading

## [2.56.1] - 2026-01-29

### Changed
- **CLAUDE.md workflow**: Added explicit STOP sign after version bump
  - Commit is now marked as MANDATORY before any new task
  - Clear instruction to respond "prima committo" if user asks for more work

## [2.56.0] - 2026-01-29

### Added
- **Auto-deregistration on failure**: SocketAgent calls `on_failure` callback when send fails
  - Dead agents are automatically removed from the list
  - When agent comes back online, discovery will re-register it
- **On-switch liveness check**: Verifies agent is alive before switching to it
  - If dead, agent is unregistered and skipped
  - Circular navigation finds next live agent
- **SocketAgent.is_alive()**: Method to check if socket has active listener

### Changed
- **Agent switching**: Now validates agent is responsive before making it current
- **ManualAgentRegistrar**: Passes `on_failure` callback to agents for auto-cleanup
- **AutoDiscoveryRegistrar**: Same auto-cleanup behavior

## [2.55.0] - 2026-01-29

### Added
- **PollingMonitor**: Reliable agent discovery via polling (default)
  - Checks socket directory every 1 second
  - Verifies sockets are alive (not just file exists)
  - Guaranteed to detect agents with 1-second delay
- **WatchdogMonitor**: Fast agent discovery via filesystem events (optional)
  - Near-instant detection but may miss events on some platforms
- **CLI `--discovery` option**: Choose discovery method
  - `--discovery polling` (default, reliable)
  - `--discovery watchdog` (fast, potentially unreliable)
- **SocketMonitor abstraction**: Pluggable monitoring strategies

### Fixed
- **Socket cleanup on agent exit**: Agent now properly removes socket file on CTRL+C
  - Bug: daemon threads don't execute `finally` blocks when process exits
  - Fix: cleanup moved to main thread's `finally` block
  - Added `atexit` handler as safety net for abnormal exits

## [2.54.0] - 2026-01-29

### Added
- **Agent as first-class concept**: Each agent handles its own transport
  - `Agent` protocol: Interface with `id` property and `send(message)` method
  - `BaseAgent`: Abstract base class for agent implementations
  - `KeyboardAgent`: Simulates keystrokes via Quartz (macOS) or ydotool (Linux)
  - `SocketAgent`: Sends messages via Unix domain socket to local processes
- **OpenVIP message format**: Standard message format with text, submit, visual_newline flags
- **Pluggable agent transports**: SSEAgent, WebhookAgent, WebSocketAgent can be added easily

### Changed
- **Engine uses Agent instances**: `register_agent(agent)` takes Agent, not string ID
- **Engine doesn't know about transports**: Just calls `agent.send(message)`
- **Registrars create Agent instances**: ManualAgentRegistrar creates SocketAgents
- **Local mode uses KeyboardAgent**: Non-agent mode now uses KeyboardAgent instead of injector

### Removed
- **Old injector architecture**: Replaced by Agent-based architecture
- **Engine._create_injector()**: Agents handle their own transport creation

## [2.53.0] - 2026-01-29

### Added
- **AgentRegistrar abstraction**: Clean separation between agent discovery and engine
  - `ManualAgentRegistrar`: Register agents from CLI args (deterministic, reliable)
  - `AutoDiscoveryRegistrar`: Watch socket directory (dynamic, uses watchdog)
- **Engine register/unregister API**: `engine.register_agent(id)` and `engine.unregister_agent(id)`
- **CLI manual agent registration**:
  - `--agents` → auto-discovery (unchanged)
  - `--agent foo --agent bar` → manual registration with specific agents

### Changed
- **Engine no longer knows about discovery mechanism**: Registrar is created and managed by app
- **Cleaner architecture**: Engine only manages agent list, discovery is pluggable

## [2.51.1] - 2026-01-28

### Fixed
- **output.method references**: Replaced remaining `output.method` with `output.mode` in cli.py and status.py

## [2.51.0] - 2026-01-28

### Added
- **Tray Output Mode dropdown**: Switch between Keyboard and Agents mode from tray menu
  - Selection shown in menu label: `Output Mode (Agents) >`
  - Persists to config when changed
- **Tray Target submenu**: Shows current target with selection: `Target (claude) >`
  - Only visible when Output Mode is Agents
- **Tray loading state**: Yellow icon during model loading with progress tracking
- **Config output.mode**: New field `output.mode = "keyboard" | "agents"` replaces deprecated `method`
- **CLI respects config mode**: `voxtype listen` uses `output.mode` from config; `--agents` flag overrides

### Changed
- **StatusResponse extended**: Added `state`, `progress`, `loading_stage` fields for tray polling

## [2.50.9] - 2026-01-28

### Fixed
- **Live panel corruption**: Removed all console.print() calls during runtime
  - Max duration, device reconnect, submit, webhook errors now use status panel
  - Verbose debug prints removed (were corrupting Live display)

## [2.50.5] - 2026-01-28

### Fixed
- **HuggingFace progress bars**: Disabled at package init (before any imports)

## [2.50.4] - 2026-01-28

### Fixed
- **HuggingFace progress bars**: Disabled via env var at module import time (didn't work)

## [2.50.3] - 2026-01-28

### Changed
- **Smart cold/warm detection**: Only saves cold load times for progress estimation
  - Warm loads (<50% of saved time) are ignored to preserve cold baseline
  - Progress bar shows accurate ETA based on cold load history

## [2.50.2] - 2026-01-28

### Changed
- **Model loading indicator**: Simplified to elapsed time only (reverted in 2.50.3)

### Fixed
- **Model loading timing**: Imports now included in timing measurement for accurate load times
- **Duplicate loading messages**: Removed redundant messages from app.py

## [2.50.0] - 2026-01-28

### Added
- **Model loading progress indicator**: Shows elapsed time during STT/VAD model loading
  - First load: spinner with elapsed time
  - Subsequent loads: progress bar with ETA based on historical times
  - Displays "STT model loaded in X.Xs" / "VAD model loaded in X.Xs" on completion
  - Load times saved to stats file for future estimates

## [2.49.0] - 2026-01-28

### Changed
- **Rich progress bars for model downloads**: HuggingFace model downloads now use existing Rich progress bars
  - Disabled ugly tqdm/HuggingFace progress bars
  - Consistent UI across all download operations

## [2.48.5] - 2026-01-28

### Fixed
- **Agent mode injection**: Socket injector now created after agent discovery
- **Keyboard typing in agent mode**: LocalReceiver no longer activates in agent mode
- **Warning when no agents**: Shows helpful message when speaking with no agents available

## [2.48.0] - 2026-01-28

### Added
- **Agent auto-discovery**: `voxtype listen --agents` now auto-discovers running agents
  - No need to specify agent names - discovers by watching socket directory
  - Real-time updates when agents start/stop (using `watchdog` filesystem watcher)
  - Stale socket detection: automatically cleans up orphaned sockets
  - Agents sorted by creation time (oldest first)
  - UI updates dynamically when agents appear/disappear
- New dependency: `watchdog>=4.0.0` for filesystem monitoring

### Changed
- **`--agents` is now a flag**: Use `voxtype listen --agents` instead of `voxtype listen --agents claude,pippo`

## [2.47.0] - 2026-01-28

### Added
- **Tray lifecycle management**: `voxtype tray start/stop/status` commands
  - Runs in background by default, use `--foreground` for debug
  - PID file management for clean start/stop
  - Graceful signal handling (SIGTERM, SIGINT)

### Changed
- **Platform-standard socket paths**: Unix sockets now use proper locations
  - Linux: `$XDG_RUNTIME_DIR/voxtype/` (typically `/run/user/UID/voxtype/`)
  - macOS: `$TMPDIR/voxtype/` (typically `/var/folders/.../T/voxtype/`)
  - Fallback: `/tmp/voxtype/`
- Added `get_runtime_dir()` and `get_socket_dir()` utilities

## [2.46.2] - 2026-01-28

### Changed
- **Tray dependencies are now standard**: pystray and Pillow (~13MB) moved from optional to core dependencies

## [2.46.1] - 2026-01-28

### Fixed
- **install.sh**: Include tray dependencies by default

## [2.46.0] - 2026-01-28

### Added
- **System tray integration**: `voxtype tray start` shows icon in menu bar
  - Cross-platform support via pystray (macOS, Linux, Windows)
  - Status indicator (idle/listening/muted) with colored icons
  - Quick controls: Start/Stop listening, Mute, Target selection
  - Fallback icons generated dynamically if PNGs not found
  - New optional dependency: `pip install voxtype[tray]`

## [2.45.0] - 2026-01-28

### Changed
- **BREAKING: `stt.model_size` → `stt.model`**: Renamed for consistency with `stt.realtime_model`
  - Update your config: `model_size = "large-v3-turbo"` → `model = "large-v3-turbo"`

## [2.44.0] - 2026-01-28

### Added
- **`voxtype models resolve`**: Auto-download all configured models with progress bars
  - Detects which models are needed based on config (STT + TTS)
  - Downloads missing ones sequentially with nice progress display

## [2.43.0] - 2026-01-28

### Added
- **Model self-check at startup**: `listen` and `daemon start` verify required models are cached
  - If models missing, shows colored model list and download commands
  - Prevents slow startup with uncached models
- **Improved `models list` display**:
  - Green: configured models that are cached
  - Red: configured models that are MISSING
  - Dim: other available models (not configured)

## [2.42.0] - 2026-01-28

### Changed
- **`voxtype check` → `voxtype dependencies`**: Renamed command with subcommands
  - `voxtype dependencies check` - Check system dependencies
  - `voxtype dependencies resolve [--dry-run]` - Auto-install missing dependencies
- **Cleaned up unused HuggingFace models**: Removed ~1.7TB of experimental TTS models from cache

### Fixed
- **Model registry**: Moved from hardcoded source to `models.json` config file

## [2.41.0] - 2026-01-28

### Added
- **`voxtype models` command**: Model management for TTS/STT
  - `voxtype models list` - Show models with cache status and size
  - `voxtype models download <model>` - Download a specific model
  - `voxtype models clear <model>` - Clear cached model(s)
  - `voxtype models clear all` - Clear all cached models

### Fixed
- **HuggingFace download progress**: Now uses `list_repo_tree` API for accurate file sizes
- **Duplicate download messages**: Removed redundant "Downloading..." messages in qwen3.py
- **VyvoTTS size estimates**: Updated to accurate values (~1GB for 4bit, not 0.3GB)

## [2.40.0] - 2026-01-28

### Added
- **Daemon architecture**: Keep models loaded in memory for instant TTS
  - `voxtype daemon start [--foreground]` - Start daemon
  - `voxtype daemon stop` - Stop daemon
  - `voxtype daemon status` - Show daemon status with uptime, requests served
  - `voxtype daemon restart` - Restart daemon
- **Fast TTS via daemon**: `voxtype speak` uses daemon if running (~900ms vs ~6s)
  - `--no-daemon` flag to force in-process TTS
  - Automatic fallback to in-process if daemon not running
- **Unix socket server**: `/tmp/voxtype-daemon.sock` with JSON protocol
- **Thread-safe TTS caching**: Models cached by engine:language:voice:speed key
- **`DaemonConfig`**: New config section for daemon settings

### Changed
- **README updated**: Added all commands (daemon, speak, agent, config, log, etc.)
- **CLI help behavior**: Commands now show help when required arguments missing

## [2.34.0] - 2026-01-28

### Added
- **OuteTTS engine**: High-quality neural TTS on Apple Silicon via mlx-audio
- **VyvoTTS via qwen3**: Rewrote qwen3 engine to use VyvoTTS (official Qwen3-TTS not working with mlx-audio)
- **mlx-audio dependencies**: Added `mlx-audio>=0.3.0` and `soundfile>=0.12.0` to `[mlx]` extras
- **HuggingFace download utility**: New `hf_download.py` with real progress monitoring via cache size
- **`--prerelease=allow`**: Added to install.sh for transformers 5.0.0rc3 (mlx-audio dependency)

### Changed
- **Download progress bars**: Now show accurate progress by monitoring HuggingFace cache directory

## [2.32.7] - 2026-01-27

### Changed
- **TapDetector refactored**: Now uses same pattern as `StateManager` for consistency
  - `TapState` Enum with 4 states: IDLE, PRESSED_1, RELEASED_1, PRESSED_2
  - `VALID_TRANSITIONS` dict defines allowed state transitions
  - Reduces cognitive load: one pattern for all state machines

### Added
- **TapDetector tests**: 22 tests covering states, single/double tap, combo abort, thread safety
  - New file: `tests/test_tap_detector.py`

## [2.32.6] - 2026-01-27

### Added
- **TapDetector**: Isolated state machine for hotkey tap/double-tap detection
  - Fixes Command+Plus (and similar combos) incorrectly triggering hotkey toggle
  - Detects when other keys are pressed while modifier is down and aborts tap
  - New file: `hotkey/tap_detector.py` (~130 lines, clean separation from engine)
- **Pluggable TTS engines**: Support for multiple text-to-speech backends
  - `say` - macOS native TTS (new)
  - `piper` - Fast neural TTS via piper-tts (new)
  - `coqui` - High-quality neural TTS via Coqui XTTS (new)
  - Config: `tts.engine = "say"` (or piper, coqui, espeak)
- **Smart install detection**: `install_info.py` detects how voxtype was installed
  - Provides correct dependency install commands for uv tool, pipx, pip, or dev mode
  - Example: `uv pip install --python ~/.local/share/uv/tools/voxtype/bin/python piper-tts`
- **Hotkey listener `on_other_key` callback**: Enables combo detection in pynput and evdev listeners

### Fixed
- **Python version constraint**: Changed from `>=3.11,<3.14` to `>=3.11,<3.12` (torch/MLX compatibility)
- **Debug prints removed**: Removed `[DEBUG FW]` prints from faster_whisper.py that appeared without --verbose

### Changed
- Hotkey tap detection logic moved from `engine.py` to dedicated `TapDetector` class
- TTS engine selection now uses factory pattern in `tts/__init__.py`

## [2.31.0] - 2026-01-27

### Added
- **`--translate` / `-T` flag**: Translate any language to English using Whisper's built-in translation
  - New CLI flag: `voxtype listen --language it --translate`
  - New config option: `stt.translate = true`
  - Works with both realtime partial transcriptions and final transcription
  - Uses Whisper's `task="translate"` (any input language → English output)

### Documentation
- Added `docs/notes/translation-options.md` with analysis of translation options (argos, ollama, nllb-200)

## [2.30.1] - 2026-01-27

### Fixed
- **Realtime partial transcriptions breaking Rich panel**: Partial transcriptions now update the status panel instead of printing directly
  - Added `update_partial()` method to `LiveStatusPanel`
  - Partial text shown in italic cyan next to status (e.g., `Status: RECORDING...  "parziale..."`)
  - Partial text cleared automatically when final transcription arrives

## [2.30.0] - 2026-01-27

### Added
- **Dual-model architecture for realtime mode**: Separate fast model for partial transcriptions
  - New config option `stt.realtime_model` (default: `tiny`) for low-latency partial transcriptions
  - Main model (e.g., `large-v3-turbo`) used for final transcription when speech ends
  - Realtime STT engine loaded lazily only when `--realtime` flag is used
  - No lock contention: realtime engine runs independently from main transcription

### Changed
- `_partial_worker_loop` now uses dedicated `_realtime_stt` engine instead of sharing `_stt`
- Reduced latency for realtime partial transcriptions (~10x faster with tiny vs large-v3-turbo)

## [2.29.3] - 2026-01-27

### Fixed
- **Unbounded queues could cause memory exhaustion**: Audio queue and event queue are now bounded
  - `_audio_queue` limited to 10 items (oldest discarded if full)
  - `_queue` (StateController) limited to 100 events (warning logged if full)
- **Silent failures in STT providers**: Model cache checks now log errors at DEBUG level instead of silently failing
  - `_is_model_cached()` in faster_whisper.py and mlx_whisper.py
- **Race condition on `_partial_text` in realtime mode**: Added lock to protect concurrent access from worker thread and transcription thread

## [2.29.2] - 2026-01-27

### Fixed
- **Stuck in TRANSCRIBING during rapid agent switching**: TTS completing while in TRANSCRIBING state now correctly transitions to LISTENING
  - Scenario: User speaks (TRANSCRIBING) → switches agent (TTS starts) → transcription completes (deferred) → TTS completes
  - Before: State stayed TRANSCRIBING forever (check was only for PLAYING state)
  - After: Check handles both PLAYING and TRANSCRIBING with pending transcription

## [2.29.1] - 2026-01-26

### Fixed
- **Concurrent TTS during rapid agent switching**: Multiple TTS can now play concurrently without state corruption
  - TTS now uses monotonic counter (`tts_id`) instead of boolean flag
  - Only the completion of the LAST TTS triggers state transition back to LISTENING
  - Prevents early return to LISTENING when first TTS completes while others still playing
  - Fixes transcription of TTS audio during rapid agent switching

## [2.29.0] - 2026-01-26

### Added
- **Event Queue Architecture**: New `StateController` for centralized state management
  - Single component responsible for ALL state transitions (FIFO processing)
  - Events: `SpeechStartEvent`, `SpeechEndEvent`, `TranscriptionCompleteEvent`,
    `TTSStartEvent`, `TTSCompleteEvent`, `HotkeyToggleEvent`, `HotkeyDoubleTapEvent`,
    `AgentSwitchEvent`, `SetListeningEvent`, `DiscardCurrentEvent`
  - All events are immutable (frozen dataclasses) with timestamp and source

### Fixed
- **TTS/Transcription race condition**: User intent preserved when pressing OFF during TTS
  - `_desired_state_after_tts` tracks what user wants after TTS completes
  - Transcription completing during TTS no longer causes state corruption
- **Concurrent state modifications**: No more race conditions from multiple threads
  - VAD, STT, TTS, hotkey, API all send events to single queue
  - Events processed sequentially by controller worker thread
- **Event ordering guaranteed**: FIFO queue ensures predictable state transitions

### Changed
- State transitions are now asynchronous (via event queue)
- VAD callbacks send events instead of direct transitions
- Hotkey handlers send events instead of direct transitions
- Agent switch sends events instead of direct transitions
- TTS sends `TTSStartEvent`/`TTSCompleteEvent` for proper state management

## [2.28.6] - 2026-01-26

### Fixed
- **Transcription goes to wrong agent after switch**: Capture injector at speech-end time
  - `_transcribe_and_process()` now captures injector BEFORE starting async transcription
  - `_inject_text()` accepts optional `injector` parameter for explicit targeting
  - Fixes race condition where `self._injector` was reassigned during async transcription

## [2.28.5] - 2026-01-26

### Fixed
- **Correct audio handling on agent switch**: Buffered speech now goes to current agent before switch
  - FLUSH VAD before switching agent (sends buffered audio to current agent)
  - RESET VAD after TTS ends (discards TTS audio only)
  - Previous behavior incorrectly discarded user speech on agent switch

## [2.28.4] - 2026-01-26

### Fixed
- **TTS captures own audio in speaker mode**: VAD buffer now reset before and after TTS playback
  - Added `AudioManager.reset_vad()` to discard buffered audio without processing
  - Reset VAD before TTS to clear pre-existing buffer
  - Reset VAD after TTS to clear audio captured during playback

## [2.28.3] - 2026-01-26

### Fixed
- **TTS race condition in speaker mode**: State transition to PLAYING now happens before starting TTS thread
  - Previously: thread started → state changed → audio still processed during gap
  - Now: state changed → thread started → no audio processed during TTS

## [2.28.2] - 2026-01-26

### Fixed
- **Status panel flickering on agent switch**: `console.print()` was breaking Rich Live display
  - Agent switch now updates the panel in-place with highlighted current agent
  - Errors shown in panel instead of printing to console

### Changed
- **Agent display**: Current agent now highlighted in green, others dimmed in panel

## [2.28.1] - 2026-01-26

### Changed
- **AudioManager refactoring**: Cleaner callable pattern using properties
  - Internal callables renamed to `_should_process_check` / `_is_running_check`
  - New properties `should_process_audio` / `is_engine_running` encapsulate None checks
  - Eliminates confusing `x = self._x() if self._x else default` pattern

## [2.28.0] - 2026-01-25

### Added
- **OpenVIP message factory**: New `src/voxtype/core/openvip.py` module
  - `create_message()`: Creates injection messages with UUID, timestamp, source
  - `create_event()`: Creates event messages (state, partial, error, etc.)
  - Single point of message creation for consistent IDs across transports

### Fixed
- **LocalReceiver thread safety**: Fixed race condition on `_injector` access between main and worker threads
- **LocalReceiver crash handling**: Worker thread now catches exceptions and logs them instead of dying silently
- **End-to-end message tracing**: Same OpenVIP ID preserved from engine through socket to mux.py

### Changed
- **Unified transport architecture**: Engine creates message once, all transports forward transparently
  - `SocketInjector.send_message()`: Forwards pre-built OpenVIP messages
  - `SSEServer.send_message()`: Broadcasts pre-built OpenVIP messages
  - `mux.py`: Preserves `openvip_id` and `openvip_ts` in session logs

### Tests
- Added 58 new tests for `LocalReceiver` and `SSEServer`

## [2.27.5] - 2026-01-25

### Changed
- **Platform-specific hotkey default**: Hotkey now defaults to Command (KEY_LEFTMETA) on macOS, Scroll Lock on Linux
- **Platform-aware config template**: `voxtype init` now creates config with correct platform defaults for hotkey and newline_keys

## [2.27.4] - 2026-01-25

### Added
- **Configurable newline/submit keys**: New config options `submit_keys` and `newline_keys` in `[output]` section
  - `submit_keys`: Key combo when `auto_enter=true` (default: "enter")
  - `newline_keys`: Key combo when `auto_enter=false` (default: "alt+enter" on Linux, "shift+enter" on macOS)
  - Supports combinations like "alt+enter", "shift+enter", "ctrl+enter"

### Fixed
- **Linux newline behavior**: Changed default from Shift+Enter to Alt+Enter, which works as visual newline in Claude and other apps (Shift+Enter was submitting in terminals)

## [2.27.3] - 2026-01-25

### Added
- **GPU install flag**: `./install.sh --gpu` installs CUDA/cuDNN on Linux (MLX already auto-enabled on macOS)
- **CPU warning in UI**: STT running on CPU now shows bold yellow on red background with hint to run `./install.sh --gpu`
- **GPU success indicator**: STT running on GPU/MLX shows in green

### Fixed
- **Installer version**: Updated install.sh version from 2.22.3 to current

## [2.27.2] - 2026-01-25

### Improved
- **User-friendly config errors**: Configuration validation errors now show a clean, readable message instead of a Python traceback. Shows the exact field, expected values, and current value.

## [2.27.1] - 2026-01-25

### Fixed
- **Audio buffer cleared on OFF**: When pressing hotkey to turn off listening, the audio buffer is now cleared. Previously, buffered audio from before OFF would be transcribed when re-enabling listening. (fixes #31)

## [2.27.0] - 2026-01-25

### Added
- **LocalReceiver**: New component for local keyboard injection via in-memory queue
  - Uniform OpenVIP message-based architecture regardless of transport
  - Engine produces OpenVIP messages, LocalReceiver consumes and injects via keyboard
- **Architecture documentation**: `docs/architecture/openvip-transport.md` describes the transport design

### Changed
- **Removed `-o`/`--output` option**: Output method is now automatic:
  - With `--agents`: uses socket transport
  - Without `--agents`: uses LocalReceiver (in-memory queue → keyboard)
- **Engine refactored for OpenVIP internally**: Always produces OpenVIP messages, local mode uses in-memory queue

## [2.26.0] - 2026-01-25

### Fixed
- **Hotkey works during RECORDING**: Pressing hotkey now correctly turns off listening from any active state (RECORDING, TRANSCRIBING, INJECTING, PLAYING), not just LISTENING/OFF
- **Double newline in socket output**: Fixed duplicate visual newlines when using `auto_enter=false` with socket/file injectors

### Changed
- **Injector termination refactor**: Each injector now handles message termination internally:
  - `auto_enter=true`: text + Enter (keyboard) / `x_submit` (socket)
  - `auto_enter=false`: text + Shift+Enter (keyboard) / `x_visual_newline` (socket)
  - Engine no longer adds `\n` to text or calls `send_newline()` - the receiver decides how to terminate

## [2.25.0] - 2026-01-24

### Added
- **Logging enabled by default**: All sessions now log to `~/.local/share/voxtype/logs/` automatically
  - `listen.jsonl` for normal sessions
  - `agent.<name>.jsonl` for agent sessions
- **Log levels**: INFO (default) and DEBUG (`--verbose`)
  - INFO: Metadata only (chars, words, duration) - no text content for privacy
  - DEBUG: Includes actual transcription text
- **`voxtype log` command**: View logs like `docker logs` or `kubectl logs`
  - `voxtype log listen [-f] [-n N] [--json]` - View listen session logs
  - `voxtype log agent NAME [-f] [-n N] [--json]` - View agent logs
  - `voxtype log list` - List all log files
  - `voxtype log path [NAME]` - Show log file path
- **Log path in status panel**: Shows current log file location in the UI
- **Webhooks**: POST transcriptions to HTTP endpoints (`--webhook URL`)
  - OpenVox-compatible JSON format with metadata
  - Async sending (non-blocking)
  - Configurable timeout via `webhook.timeout`
- **Server-Sent Events (SSE)**: Stream events to clients (`--sse`)
  - Real-time event streaming at `http://localhost:8765/events`
  - Events: transcription, state_change, mode_change, agent_change, partial_transcription, error
  - OpenVox-compatible message format
  - Configurable port via `--sse-port`

### Changed
- **JSONLLogger**: Added `LogLevel` enum (ERROR, INFO, DEBUG) with privacy-aware logging
  - Transcriptions at INFO level log only metadata (chars, words, duration)
  - Text content requires DEBUG level (`--verbose`)
- **Status panel**: New "Log:" line shows log file path (shortened with ~/)

## [2.24.4] - 2026-01-24

### Added
- **VoxtypeEngine**: New core engine class (`src/voxtype/core/engine.py`) with all business logic and NO UI dependencies
- **EngineEvents protocol**: Event-based architecture (`src/voxtype/core/events.py`) for decoupling core from UI
  - `on_state_change`, `on_transcription`, `on_injection`, `on_mode_change`, `on_agent_change`
  - `on_vad_loading`, `on_device_reconnect_attempt`, `on_device_reconnect_success`
- **Unit tests for engine**: 47 new tests in `tests/test_engine.py`

### Changed
- **VoxtypeApp refactored**: Now a thin wrapper (~550 lines) that implements `EngineEvents` and handles UI only
- **AudioManager UI-free**: Removed `console` parameter, added event callbacks instead (`on_vad_loading`, `on_reconnect_attempt`, `on_reconnect_success`)

### Fixed
- **Stuck in TRANSCRIBING**: Engine now emits `on_state_change` event after `reset_to_listening()` so UI updates correctly
- **Graceful cleanup**: Added try/except for `rich.columns` import during session stats display

## [2.23.0] - 2026-01-24

### Changed
- **TTS code deduplicated**: New `_speak_text()` helper method replaces ~40 lines of duplicate code in `_speak_mode_with_mute()` and `_speak_agent()`
- **Queue processing iterative**: Converted `_process_queued_audio()` from recursive to iterative loop (fixes #26)

### Fixed
- **Partial transcription logging**: Errors in realtime transcription are now logged in verbose mode instead of being silently swallowed (fixes #27)

### Removed
- **Dead code cleanup**: Removed unused `_speech_was_ignored` variable and `_signal_ready_to_listen()` method (~20 lines) - variable was never set to `True` (fixes #25)

## [2.22.3] - 2026-01-24

### Added
- **Live status panel**: New Rich Live-based UI that updates in-place without scrolling
  - Fixed-width panel (72 chars) prevents resizing on content change
  - Color-coded status: OFF (dim), LISTENING (green), RECORDING (cyan), TRANSCRIBING (yellow), INJECTING (magenta), PLAYING (blue)
  - Shows last transcribed text (truncated to 55 chars)
  - Title shows version: "voxtype vX.Y.Z"
- **`--force` flag for install.sh**: Force rebuild from source even with same version (for developers)

### Fixed
- **Duplicate panel on Ctrl+C**: Panel was rendered twice on shutdown. Now stopped in `app.stop()` before any console output.
- **Consistent Python 3.11 on Linux**: Linux install was missing `--python 3.11`, now matches macOS for identical UX.

## [2.22.0] - 2026-01-24

### Added
- **Open source readiness**: Project is now ready for public contribution
  - `CONTRIBUTING.md`: Development setup, testing, code style, and PR process
  - `CODE_OF_CONDUCT.md`: Community guidelines
  - `SECURITY.md`: Vulnerability reporting policy
  - `.github/ISSUE_TEMPLATE/`: Bug report and feature request templates
  - `.github/PULL_REQUEST_TEMPLATE.md`: PR template
  - `.github/workflows/ci.yml`: GitHub Actions CI (tests + linting on push/PR)

### Fixed
- **Test suite**: Updated tests to use new state machine API (`OFF`/`LISTENING` instead of `IDLE`, `reset_to_listening()` instead of `reset()`)
- **Dev dependencies**: Added `typer` to dev dependencies for CLI tests

## [2.21.2] - 2026-01-24

### Fixed
- **Critical: "Not listening, ignoring" bug**: Transcriptions were always ignored because `is_listening` returned `False` during `TRANSCRIBING` state. Fixed by checking `is_off` instead - we only ignore if user explicitly turned off the mic.

## [2.21.1] - 2026-01-24

### Changed
- **Renamed config**: `audio.tts_pauses_listening` → `audio.headphones_mode` (default `false`). More intuitive naming - set to `true` when using headphones.

## [2.21.0] - 2026-01-24

### Changed
- **Unified state machine**: The `_listening` boolean flag is now part of the state machine. States: `OFF` (mic disabled), `LISTENING` (mic active), `RECORDING`, `TRANSCRIBING`, `INJECTING`, `PLAYING`. This eliminates race conditions between the flag and state transitions.
- **Renamed `IDLE` → `OFF`**: The idle state is now called `OFF` to clearly indicate the mic is disabled. `LISTENING` is the new "ready" state.
- **Conditional TTS behavior**: New config `audio.headphones_mode` (default `false`):
  - `false` (speakers): TTS transitions to `PLAYING` state, pausing mic to prevent echo capture
  - `true` (headphones): TTS fires in background, mic keeps listening
- **VAD flush after TTS**: When returning from `PLAYING` to `LISTENING`, VAD is flushed to clear any residual echo in the audio buffer.

### Fixed
- **TTS echo capture bug**: When using speakers, the TTS feedback (e.g., "agent pippo") was being picked up by the mic and transcribed. Now properly blocked via the `PLAYING` state.

### Removed
- **`_listening` flag**: Replaced by state machine. Use `is_listening` property or check `state == AppState.LISTENING`.
- **`_state_lock`**: State synchronization now handled entirely by `StateManager`.

## [2.20.1] - 2026-01-24

### Fixed
- **Consistent lock for `_listening` flag**: Added `is_listening` property that acquires `_state_lock` for thread-safe reads. Writes were already protected; now reads are too.

## [2.20.0] - 2026-01-24

### Changed
- **Partial transcription uses queue**: Replaced spawn-thread-per-chunk with single worker thread consuming from a queue. Eliminates race condition where multiple threads could call MLX concurrently. Worker drains queue to always process latest chunk, avoiding lag.

## [2.19.0] - 2026-01-24

### Changed
- **Dead code cleanup**: Removed unused `messages.py` (89 lines) and unused exception classes from `errors.py`
- **Deduplicated HID_KEY_MAP**: Extracted to `input/constants.py`, imported by both `device.py` and `hidapi_backend.py`

### Fixed
- **Broken import in terminal.py**: Fixed import path from non-existent `voxtype.output.injector` to `voxtype.injection.base`

## [2.18.10] - 2026-01-24

### Fixed
- **Pin sounddevice <0.5.4**: Version 0.5.4 (released 2026-01-21) has a bug in `finished_callback` that causes `AttributeError: '_CallbackContext' object has no attribute 'out'` on every audio stream completion.
- **Double Ctrl+C semaphore warning**: Pressing Ctrl+C twice quickly no longer shows "leaked semaphore objects" warning. The multiprocessing resource tracker process is killed before force exit to suppress the cosmetic warning (the kernel cleans up the semaphore anyway).

## [2.18.7] - 2026-01-21

### Fixed
- **PTY write reliability**: Added `_write_all()` to handle short writes - ensures all bytes are written even if OS returns partial write.
- **Accurate session logging**: `msg_sent` is now logged AFTER the actual write completes, not before. Adds `bytes` field showing actual bytes written.
- **Agent no longer truncates .voxtype file**: The agent now preserves existing file content instead of truncating on startup. It only creates the file if it doesn't exist.

### Changed
- **PTY write delay increased to 100ms**: Increased delay between writes from 5ms to 100ms to give target applications (like Claude Code) time to process input. Fixes dropped phrases issue.
- **Version single source of truth**: Version is now only defined in `__init__.py`, read dynamically by pyproject.toml via hatch.

### Added
- **tcdrain() after PTY writes**: Ensures bytes are transmitted to the slave side before proceeding.

## [2.18.3] - 2026-01-21

### Fixed
- **Critical race condition in file reader**: `readline()` could return partial lines when called mid-write, causing JSON parse failures and silent data loss. Now buffers incomplete lines until newline is received.
- **TTS self-transcription**: Added `PLAYING` state to state machine - audio processing is blocked during TTS playback to prevent transcribing voice feedback.

### Added
- **Queue-based PTY serialization**: Both stdin and file reader threads now write to a thread-safe queue, with a single consumer thread writing to PTY. Eliminates race conditions from concurrent writes.
- **Message timestamps and versioning**: Every message in `.voxtype` file now includes `ts` (ISO timestamp) and `v` (voxtype version) for debugging.
- **Session logging**: Every message read and sent is logged to session file with sequence numbers, timestamps, and writer version.
- **Keystroke counter**: Tracks keyboard input for voice vs keyboard usage statistics (privacy-preserving - only counts, no content).
- **Lifetime keystroke stats**: `total_keystrokes` added to persistent stats for long-term voice/keyboard ratio tracking.

## [2.16.5] - 2026-01-20

### Fixed
- **Thread safety**: Added `_state_lock` for `_listening`/`_running` flags in app.py
- **Audio queue race condition**: Replaced raw list with thread-safe `queue.Queue` in AudioManager

### Added
- **Lifetime stats**: Persistent statistics stored in `~/.local/share/voxtype/stats.json`
  - Tracks total transcriptions, words, characters, time saved across all sessions
  - Shows "All time: X hours saved across Y sessions (since DATE)" on exit
  - First use date recorded automatically

## [2.16.0] - 2026-01-20

### Fixed
- **Virtualized macOS detection**: Automatically detect and disable MLX acceleration in VM environments (UTM, Parallels, VMware)
  - Prevents Metal kernel errors (`unsupported deferred-static-alloca-size`)
  - Shows clear warning message when VM is detected
- **Ghostty terminal newline**: Changed from Shift+Return to Alt+Return (Option+Return) for visual newlines
  - Fixes escape sequence bug `[27;2;13~` appearing at end of lines in Ghostty
  - More reliable across all macOS terminal emulators (iTerm2, Terminal.app, Alacritty, WezTerm)
- **Terminal compatibility**: Improved Rich Console initialization for better compatibility across terminals
  - Added `safe_box=True` for safer box drawing characters
  - Better handling of terminal capabilities

### Added
- **Escape sequence sanitization**: Defense layer that filters ANSI escape sequences and control characters from injected text
  - Prevents spurious escape codes from appearing in typed text
  - Preserves Unicode, whitespace, and newlines
- **Documentation**: Added `TERMINAL_COMPATIBILITY.md` and `GHOSTTY_NEWLINE_FIX.md` guides

## [2.15.3] - 2026-01-17

### Fixed
- **Version display**: Sync `__version__` in `__init__.py` with `pyproject.toml`

## [2.15.2] - 2026-01-17

### Fixed
- **Semaphore leak**: Use threading.Lock to properly synchronize VAD access during shutdown (#23)
- **Config shortcuts**: Create config directory if missing when saving shortcuts (#24)

## [2.15.1] - 2026-01-11

### Fixed
- **Self-listening bug**: Mode switch TTS no longer gets transcribed (mic muted during speech)
- **LLM processor sync**: State now properly synced at startup and mode switch
- **Semaphore leak**: Improved shutdown synchronization to prevent ONNX semaphore leaks

### Added
- **Configurable TTS phrases**: Create `~/.config/voxtype/tts_phrases.json` to customize voice feedback
- **English defaults**: TTS now says "transcription mode", "command mode", "agent" by default

## [2.15.0] - 2026-01-09

### Added
- **Realtime mode** (`--realtime` / `-R`): Shows transcription progressively while speaking
- **Session stats**: Display output stats (words, WPM) and timing breakdown on exit
- **Config option**: `stats.typing_wpm` for time-saved calculation (default 40 WPM)

### Changed
- **Shutdown**: Proper ONNX cleanup, 3-second timeout, double Ctrl+C force exit

## [2.14.5] - 2026-01-09

### Changed
- **CLI output**: Panels and tables no longer expand to full terminal width
- **CLI output**: Replaced "Checking dependencies..." panel with simple text (panels reserved for important results)

## [2.14.4] - 2026-01-09

### Changed
- **CLI output**: Panels and tables no longer expand to full terminal width
- **CLI output**: Added spacing (newlines) around boxes for cleaner display

## [2.14.3] - 2026-01-09

### Changed
- **CLI errors**: Simple text errors instead of giant Rich boxes

## [2.14.2] - 2026-01-09

### Fixed
- **Shell completion**: Use Typer's completion format instead of Click's (was generating incompatible scripts)

## [2.14.1] - 2026-01-09

### Fixed
- **Shell completion**: Enable runtime completion support (add_completion=True)

## [2.14.0] - 2026-01-09

### Added
- **Shell completion**: `voxtype completion install/show/remove` commands for bash, zsh, and fish

## [2.13.0] - 2026-01-09

### Added
- **StateManager**: Explicit state machine with validated transitions (IDLE→RECORDING→TRANSCRIBING→INJECTING→IDLE)
- **AudioManager**: Encapsulated audio capture, VAD, and audio queue management into dedicated class

### Changed
- **Architecture refactoring**: Extracted state and audio management from VoxtypeApp (1142→1054 lines)
- **Thread safety**: StateManager handles its own locking, removed redundant `_lock` from app
- **STT interface**: Documented `hotwords` and `beam_size` as optional (may be ignored by MLX engine)

### Removed
- Dead code: `_init_components()`, `_create_audio_capture()` methods
- Redundant `_lock` threading lock (now in StateManager)

## [2.12.5] - 2026-01-09

### Fixed
- **Documentation**: Replace stale `voxtype run` with `voxtype listen` in README and install.sh
- **CLI help**: Remove non-existent `submit` command from `voxtype cmd` help
- **CLI error**: Fix error message to suggest `voxtype listen` instead of `voxtype run`
- **Config**: Remove stale `controller` references from config utilities
- **beam_size**: Connect config option to transcription (was defined but unused)

### Removed
- Stale `CONTROLLER_*` message constants from messages.py

## [2.12.4] - 2026-01-08

### Added
- **Anti-hallucination filter**: Filters out repetitive Whisper hallucinations (e.g., "la la la la la...") that occur with background noise or silence
- **`stt.max_repetitions` config option**: Maximum consecutive word repetitions before filtering (default: 5)

## [2.12.3] - 2026-01-07

### Added
- **`mute_mic_during_feedback` option**: Pause listening while playing voice feedback to prevent mic from picking up TTS output (useful when using speakers)

### Fixed
- **TOML config write format**: `_save_shortcuts` now writes proper TOML syntax instead of Python dict syntax
- **Keyboard listener cleanup**: Added `join(timeout=2.0)` to properly wait for listener threads to stop
- **ParamType enum**: Fixed `INTEGER` -> `INT` typo in `switch-to-project-index` command

### Changed
- **Simplified shortcuts UI**: Replaced Rich TUI with simple text-based interface for reliability
- **Config command help**: Now shows help by default instead of listing all options

## [2.12.2] - 2026-01-04

### Added
- **Interactive shortcut configuration**: `voxtype config shortcuts` opens an interactive TUI to configure keyboard shortcuts
- **New `src/voxtype/ui/` module**: Reusable interactive UI components
- **`switch-to-project-index` command**: Switch to agent by number (1-based)

### Changed
- **No default keyboard shortcuts**: Users configure their own shortcuts to avoid system conflicts (Ctrl+Alt+N conflicts with GNOME workspaces, Ctrl+Shift+N produces Unicode on macOS)

### Removed
- **Pre-configured keyboard shortcuts**: Removed to avoid platform-specific conflicts

## [2.12.1] - 2026-01-04

### Added
- **`switch-to-project-index` command**: Switch to agent by number (1-based)
- Initial keyboard shortcuts (later removed in 2.12.2)

## [2.12.0] - 2026-01-04

### Added
- **`voxtype agent` command**: Wrap any command with voxtype voice input (integrates inputmux functionality)
  ```bash
  # Terminal 1: Start the agent
  voxtype agent macinanumeri -- claude -c

  # Terminal 2: Send voice input
  voxtype listen --agents macinanumeri
  ```

### Changed
- **BREAKING: `voxtype run` renamed to `voxtype listen`**: Symmetric with `voxtype speak`
- **Default output_dir is now `/tmp`**: When using `--agents`, files are created in `/tmp/<agent>.voxtype`

## [2.11.3] - 2026-01-04

### Fixed
- **Injection race condition**: Added `_injection_lock` to serialize CGEventPost calls from concurrent transcription threads
- **auto_enter=false not working**: Changed visual newline from Option+Return to Shift+Return (compatible with more apps)
- **30 second startup with no feedback**: Show "Loading STT model..." and "Loading VAD model..." messages during initialization
- **Ready panel timing**: Status panel now displays AFTER model loading completes, not before
- **Slow MLX check**: Use `importlib.find_spec` instead of importing mlx_whisper (instant vs 5+ seconds)

### Changed
- **Status panel UX**: Added "Hotkey:" prefix for clarity

## [2.11.2] - 2026-01-04

### Changed
- **README simplified**: Minimal install/run instructions, advanced features discoverable via `--help` and `docs/`
- **ARCHITECTURE.md updated**: Reflects current simplified architecture (removed PTT mode, legacy backends)
- **Code comments cleaned**: Removed outdated references to xdotool, clipboard, push-to-talk

### Fixed
- **docs/LLM_ARCHITECTURE.md**: Updated model name from llama3.2:1b to qwen2.5:1.5b

## [2.11.1] - 2026-01-04

### Added
- **Python environment check**: Detects when voxtype runs with wrong Python version (e.g., via pyenv shim or uv run alias) and shows helpful UX panel with fix instructions

### Fixed
- **Double output bug**: Text was typed twice on macOS due to Quartz injector setting Unicode string on both key-down and key-up events
- **Race condition**: "LISTENING ON" message now appears before audio processing starts, ensuring user sees feedback first
- **install.sh improvements**:
  - Uses `--reinstall` for clean upgrades without manual cache cleaning
  - Fixed ANSI escape codes (use `echo -e` for bold text)
  - Removed non-existent `--vad` flag from usage suggestions

## [2.11.0] - 2026-01-03

### Changed
- **Simplified text injection**: Removed legacy injection backends, keeping only the essential ones:
  - **Linux**: `ydotool` only (universal, works on X11/Wayland/TTY)
  - **macOS**: `quartz` only (Quartz events, best Unicode support)
  - **Agent mode**: `file` injector for inputmux integration

### Removed
- **Deprecated injection backends**: `wtype`, `xdotool`, `macos` (AppleScript), `clipboard`
- **Clipboard output mode**: Use `keyboard` or `agent` mode instead
- **Fallback chain**: Each platform now has one clear injector. If unavailable, clear error with fix instructions.

### Fixed
- **Hardware detection refactored**: MLX/CUDA detection logic extracted to `utils/hardware.py` for DRY code

## [2.10.0] - 2026-01-03

### Added
- **Modular device backend architecture**: Clean separation of input backends in `input/backends/`
  - `evdev`: Linux-only with exclusive device grab
  - `hidapi`: Cross-platform HID access (no grab)
  - `karabiner`: macOS-only using Karabiner-Elements for exclusive device grab
- **`voxtype cmd`**: Send commands to running voxtype via Unix socket (for external tools like Karabiner)
- **`voxtype backends`**: List available device input backends on current system
- **Karabiner-Elements integration**: Auto-generates Karabiner config for device grab on macOS

### Changed
- **Comprehensive dependency docs**: README now has full tables for Core, macOS, and Linux dependencies
- **Device profile docs**: Backend table, Karabiner setup instructions, platform support details

## [2.9.0] - 2026-01-03

### Added
- **macOS HID device support**: Presenter remotes and macro pads now work on macOS via hidapi
- **`voxtype devices` on macOS**: Lists HID devices with vendor/product IDs for profile creation
- **Device profile documentation**: README updated with full device profile guide

### Changed
- **hidapi package**: Using `hidapi>=0.14.0` which bundles native library (no `brew install` needed)

## [2.8.0] - 2026-01-03

### Changed
- **Command orchestrator architecture**: Refactored input handling into clean, modular system
  - `commands/`: AppCommands for app-level commands, CommandSchema for JSON schemas
  - `executors/`: LLMAgentExecutor (JSONL output), TerminalExecutor (keyboard inject)
  - `input/`: InputManager, KeyboardShortcutSource, DeviceInputSource
- **Device profiles**: Configure dedicated devices (presenter, macro pad) via TOML files in `~/.config/voxtype/devices/`
- **Platform dependencies auto-installed**: pynput/pyobjc on macOS, evdev on Linux - no more optional extras needed

### Removed
- **Old controller system**: Replaced `presenter_controller.py` and `controller_listener.py` with device profiles
- **`--set-controller` CLI option**: Use device profiles instead

### Fixed
- **macOS stability**: Platform dependencies now required, preventing missing pynput issues

## [2.7.0] - 2026-01-02

### Added
- **PresenterController**: New controller type for clicker/presenter remotes. Ignores modifier keys (Shift, Ctrl, Alt, Meta) and maps presenter buttons to commands transparently.
- **`controller.type` config**: Choose between `presenter` (clicker remotes) or `generic` (custom key mappings for programmable keypads).

### Fixed
- **Debounce for presenter remotes**: Single button press on presenter remotes sends multiple keys (F5, B, P, S, etc.). Added 300ms debounce window to prevent multiple commands from single press.
- **Device selection**: PresenterController now prefers keyboard devices (`kbd` in by-id symlink) over system control devices.
- **Double newline bug**: FileInjector was writing two newlines per phrase. Now correctly writes one.
- **Controller logs in verbose only**: Controller debug messages now only show with `--verbose`.

## [2.6.0] - 2026-01-02

### Changed
- **JSONL protocol for file output**: FileInjector now writes JSONL instead of plain text. Each line is a JSON object with `text` and optional `submit` flag. Trailing `\n` in text = visual newline (Alt+Enter). Requires inputmux v0.3.0+.

## [2.5.2] - 2026-01-02

### Changed
- **File protocol for inputmux**: Clean protocol where `\n` = visual newline (Alt+Enter) and `<<SUBMIT>>` = submit (Enter). Inputmux interprets and translates.

## [2.5.1] - 2026-01-02

### Fixed
- **FileInjector ignoring auto_enter=false**: In agents mode, transcriptions were always submitting (Enter) even with `auto_enter = false`. Now respects the setting - when false, text accumulates without submitting.

## [2.5.0] - 2026-01-02

### Changed
- **Cleaner startup output**: Status box shows immediately, verbose messages only with `--verbose`
- **Removed redundant "Ready!" message**: Box title already says "Ready"
- **Verbose-only messages**: "Initializing...", "Loading STT...", "Loading VAD...", "LLM processor...", "Controller...", "Hotkey device..." now only shown with `--verbose`

### Removed
- **"CUDA GPU detected" message**: Info already in status box, no need to print separately

## [2.4.0] - 2026-01-02

### Added
- **`voxtype devices` command**: List input devices and configure hotkey/controller device interactively
- **`hotkey.device` config**: Specify which keyboard to use for hotkey (empty = auto-detect)
- Devices with "keyboard" in name shown first, easier to find your keyboard

### Usage
```bash
voxtype devices                    # List all devices
voxtype devices --set-hotkey       # Select device for hotkey
voxtype devices --set-controller   # Select device for controller
```

## [2.3.0] - 2026-01-02

### Changed
- **Consolidated --verbose and --debug**: Now just `--verbose` (or `-v`) for all debug/verbose output
- **Removed `logging.debug` config**: Use `verbose` at top level instead

### Added
- **messages.py**: Centralized user-facing messages for consistency and easier maintenance

## [2.2.2] - 2026-01-02

### Fixed
- **Hotkey selecting wrong device**: Now prioritizes devices with "keyboard" in the name, so presenters/clickers won't be selected over real keyboards

## [2.2.1] - 2026-01-02

### Fixed
- **Hotkey not working**: `is_key_available()` now uses same device filtering as `_find_keyboard_device()`, preventing false positives when key exists only on virtual/excluded devices
- **Logger crash**: Fixed reference to removed `config.audio.vad` in `_create_logger()`

## [2.2.0] - 2026-01-02

### Removed
- **`auto_paste` config option**: Clipboard mode now always auto-pastes (Ctrl+V)
- **PTT (Push-to-Talk) mode**: Only VAD mode now, simplifies codebase
- **`--vad` flag**: Always VAD, no need to specify
- **`audio.vad` config**: Removed (always true now)

### Changed
- **`--key` → `--hotkey`**: Clearer naming for toggle listening key
- **Wake word auto-added to hotwords**: If you set `wake_word = "hey joshua"`, it's automatically added to STT hotwords

### Added
- **Hotwords in STT transcribe**: `stt.hotwords` now passed to faster-whisper for better recognition
- **Wake word → hotwords merge**: Wake word is automatically included in hotwords

## [2.1.0] - 2026-01-02

### Changed
- **Terminology: projects → agents**: More aligned with multi-agent use case
  - `--projects` → `--agents`
  - `project_next`/`project_prev` → `agent_next`/`agent_prev` (controller commands)
  - File extension: `.transcription` → `.voxtype`
- **Output mode `file` → `agent`**: `--output agent` writes to `<agent>.voxtype` files
- **`--mode` → `--initial-mode`**: Clarifies it's the starting mode (can be switched at runtime)
- **Input mode naming**: "Push-to-talk" → "Manual" (clearer for non-VAD mode)
- **Language default is always `auto`**: No hardcoded language

### Added
- **`stt.hotwords`**: Comma-separated words to boost recognition (e.g., `voxtype,joshua`)
  - Helps with custom vocabulary that Whisper doesn't recognize well

### Removed
- **`--output-file`**: No longer needed, filename derived from agent ID

## [2.0.0] - 2026-01-02

### BREAKING CHANGES
- **Config section renamed**: `[injection]` → `[output]`
- **Config key renamed**: `injection.backend` → `output.method` with values `keyboard|clipboard|file`
- **CLI options changed**:
  - `--clipboard`, `--keyboard` → `--output keyboard|clipboard|file`
  - `--mlx`, `--no-accel` → `--hw-accel=true|false`
  - `--no-commands` → `--commands=true|false`
  - `--vad/--ptt` → `--vad=true|false`

### Removed
- **`fallback_to_clipboard`**: No longer needed, output method is explicit
- **`--mlx` flag**: MLX is auto-detected on Apple Silicon

### Added
- **All CLI options now in config**:
  - `audio.vad` - VAD mode (true) or push-to-talk (false)
  - `audio.silence_ms` - VAD silence duration in milliseconds
  - `command.wake_word` - Wake word to activate
  - `command.mode` - Processing mode (transcription|command)
  - `logging.debug` - Debug mode
  - `logging.log_file` - JSONL log file path
  - `stt.hw_accel` - Hardware acceleration (auto-detect)
- **New `[logging]` config section** for debug and log_file

### Changed
- **Simplified output method selection**: Choose between `keyboard`, `clipboard`, or `file`
  - Internal backend (ydotool/wtype/xdotool/quartz/macos) is auto-detected
- **Boolean flags are explicit**: Use `--flag=true` or `--flag=false`

### Migration
Delete your existing config file and run `voxtype init`:
```bash
rm ~/.config/voxtype/config.toml
voxtype init
```

## [1.7.2] - 2026-01-02

### Fixed
- **Config `injection.backend` now respected**: Status panel now shows actual backend from config, not just CLI flag
- **Output display**: Shows actual backend name (ydotool, clipboard, etc.) instead of generic "keyboard"

## [1.7.1] - 2026-01-02

### Fixed
- **Visual newline in keyboard mode**: Now calls `send_newline()` (Alt+Enter) after each transcription when `auto_enter=false`

## [1.7.0] - 2026-01-02

### Added
- **Separate newline vs submit methods on all injectors**:
  - `send_newline()` - visual line break without submitting (Alt+Enter on keyboard)
  - `send_submit()` - submit/send the text (Enter key)
- **Controller `send` command**: Map a controller button to manually submit text
- **Full backend support**:
  | Backend | send_newline | send_submit |
  |---------|--------------|-------------|
  | ydotool | Alt+Enter | Enter |
  | xdotool | alt+Return | Return |
  | wtype | Alt+Return | Return |
  | clipboard | Alt+Enter | Enter |
  | file | `\n` | `---SUBMIT---` marker |
  | macos | Option+Return | Return |
  | quartz | Option+Return | Return |

### Changed
- **TextInjector base class**: Added `send_newline()` and `send_submit()` abstract methods

## [1.6.0] - 2026-01-02

### Added
- **VAD max speech duration**: In VAD mode, speech is now chunked at `max_duration` (default 60s)
  - Sends transcription and continues listening
  - Plays beep to notify user
- **`voxtype check` shows GPU status**: Detects NVIDIA GPU and cuDNN availability
- **Hardware acceleration hints**: Shows exact install command when GPU detected but cuDNN missing
- **Turbo model download message**: Shows "Downloading... This may take a few minutes"

### Changed
- **Ready box shows actual device**: Now shows "CPU (GPU detected, cuDNN missing)" instead of "GPU (CUDA)"
- **Default `typing_delay_ms`**: Changed from 3 to 5 for better compatibility

### Fixed
- **`config set` nested dicts**: Now writes TOML subsections correctly (was writing Python dict syntax)
- **Graceful CPU fallback**: No more crashes when cuDNN missing, uses int8 compute type
- **VAD max duration beep**: Fixed ImportError using correct `play_beep_sent()` function

## [1.5.0] - 2026-01-02

### Changed
- **Hardware acceleration is now auto-detected by default** - CUDA on Linux, MLX on macOS
- **New `--no-accel` flag** replaces `--gpu` - use to force CPU mode
- **Config `stt.device` default**: Changed from `"cpu"` to `"auto"`
- **Model download progress bar**: Shows download progress when fetching Whisper models

### Fixed
- **Turbo model support**: `turbo` and `large-v3-turbo` models now work correctly (handled natively by faster-whisper)
- **HuggingFace auth errors**: Clear error messages with troubleshooting steps for download failures

### Removed
- **`--gpu/-g` flag**: No longer needed since GPU is auto-detected (use `--no-accel` to disable)

## [1.4.4] - 2026-01-02

### Added
- **Automatic CUDA setup**: Pre-loads cuDNN libraries automatically before importing ctranslate2
- **Graceful GPU fallback**: Falls back to CPU if CUDA/cuDNN fails, with clear error messages
- **`cuda_setup.py`**: New module for GPU initialization with helpful remediation steps

### Fixed
- **cuDNN version pinned**: `nvidia-cudnn-cu12>=9.1.0,<9.2.0` to match ctranslate2 requirements
- **No more `LD_LIBRARY_PATH`**: GPU acceleration works out of the box

## [1.4.3] - 2026-01-02

### Added
- **`--quiet/-q`**: Suppress all status messages for pure pipe mode
- **`--show-text/-t`**: Echo transcription on stderr before LLM response (default: true)

### Fixed
- **Ctrl+C handling**: Properly stops audio stream on interrupt
- **Clean output**: Suppress progress bars during model loading

## [1.4.2] - 2026-01-02

### Added
- **`voxtype transcribe`**: One-shot transcription command for piping to other tools
  - Perfect for `voxtype transcribe | llm "respond"`
  - VAD auto-detects speech start/end
  - Output to stdout (for pipes) or file (`-o`)

## [1.4.1] - 2026-01-02

### Added
- **Piper TTS**: High-quality neural voice for project announcements (Italian "Paola" voice)
- **"Sent" beep**: Ascending double-beep when transcription is written to file
- **TTS fallback chain**: piper → spd-say → espeak-ng → espeak

### Fixed
- **Controller device selection**: Now selects device with matching keys (not just by name)
- **Exclusive device grab**: Controller keys no longer go to terminal
- **Hotkey device conflict**: Excludes controller device from hotkey listener
- **Device handle leaks**: Properly closes unused evdev devices

## [1.4.0] - 2026-01-01

### Added
- **Multi-project support**: `--projects` option for multiple output targets (comma-separated)
- **Output directory**: `--output-dir` for project transcription files (`<dir>/<project>.transcription`)
- **Controller device**: `--controller` option to use a Bluetooth presenter/clicker for project switching
- **Controller commands**: listening_on, listening_off, project_next, project_prev, discard
- **TTS feedback**: Speaks project name when switching
- **Config section**: `[controller]` with device name and key mappings

### Changed
- Projects mode creates files on startup so inputmux can find them

## [1.3.10] - 2026-01-01

### Fixed
- **File injection duplicate newline**: Removed extra newline that caused issues with inputmux integration

## [1.3.9] - 2026-01-01

### Fixed
- **"Listening..." always shown**: VAD now shows "Listening..." whenever speech is detected, including during buffering

### Removed
- **Busy beep**: No longer needed since buffering works and "Listening..." is always shown

## [1.3.8] - 2026-01-01

### Fixed
- **Audio buffering during transcription**: Speech during transcription is now queued and processed afterward instead of discarded

## [1.3.7] - 2026-01-01

### Fixed
- **Ready-to-listen feedback**: Restored audio feedback after transcription when speech was ignored (#17)

## [1.3.6] - 2026-01-01

### Added
- **File output mode**: `--output-file` / `-F` to write transcriptions to a file (in addition to keyboard/clipboard)

## [1.3.5] - 2026-01-01

### Refactored
- **Reduced cyclomatic complexity**: All E/D rated functions now A/B
  - `cli.py:run`: E(35) → A(3) by extracting `_create_logger()`, `_auto_detect_acceleration()`, `_apply_cli_overrides()`, `_format_status_panel()`
  - `platform.py:check_dependencies`: E(33) → A(3) by extracting category-specific checkers
  - `processor.py:_parse_ollama_response`: D(26) → A(4) by extracting `_build_response_from_json()`, `_validate_response()`, `_validate_listening_response()`, `_validate_idle_response()`
- **Average complexity**: A (3.17) across 265 functions

## [1.3.4] - 2025-12-31

### Fixed
- **macOS hotkey**: Auto-detect platform and use Right Command (⌘) on macOS instead of ScrollLock

## [1.3.3] - 2025-12-31

### Fixed
- **auto_enter default**: Fixed example config to use `auto_enter = true` (Enter is default behavior)

## [1.3.2] - 2025-12-31

### Fixed
- **Documentation**: Fixed platform notes - keyboard mode is default, not clipboard

## [1.3.1] - 2025-12-31

### Changed
- **VAD as default**: VAD mode is now the default, use `--ptt` for push-to-talk

### Fixed
- **CUDA detection**: Use `get_cuda_device_count()` for more reliable GPU detection on Linux

## [1.3.0] - 2025-12-31

### Added
- **ProcessingMode enum**: Type-safe mode switching (transcription/command)
- **Tests**: 16 new tests for config and CLI modules
- **Constants**: `DEFAULT_VAD_SILENCE_MS`, `HISTORY_WINDOW_SIZE` for better maintainability
- **set_listening() method**: Proper API for LLM processor state management

### Changed
- **Auto-detect CUDA**: Uses ctranslate2 instead of torch for GPU detection on Linux
- **--enter → --no-enter**: Enter is now default behavior, use --no-enter to disable
- **Exception handling**: Replaced broad `except Exception` with specific exceptions
- **State consolidation**: Single source of truth for app state

### Fixed
- **Duplicate AppState enum**: Removed from llm/models.py, now imports from core/state
- **Italian strings**: Removed hardcoded Italian from llm/models.py
- **Unused parameters**: Prefixed with underscore per Python conventions
- **Bare print()**: Replaced with sys.stderr.write() in hotkey listener

### Refactored
- Major code cleanup for open-source publication
- Version sync (pyproject.toml + __init__.py)

## [1.2.0] - 2025-12-31

### Changed
- **Default model**: Changed from `base` to `large-v3-turbo` for better accuracy
- **Auto-detect GPU**: Automatically use CUDA on Linux if available
- **Auto-detect MLX**: Already detecting on Apple Silicon, now also for GPU

## [1.1.0] - 2025-12-31

### Added
- **Voice feedback for mode switching**: TTS announces mode changes
  - macOS: Uses `say` command with language-appropriate voices
  - Linux: Uses espeak-ng, espeak, or spd-say
  - Supports Italian and English

### Fixed
- **Double-tap detection**: Fixed issue where double-tap triggered both single-tap and mode switch
  - Uses timer to delay single-tap action, allowing cancellation on second click
- **Beep sounds**: Restored beep sounds by using correct function names
- **Hotkey display**: Shows configured hotkey in Ready panel

## [1.0.22] - 2025-12-31

### Added
- **Hotkey display**: Show configured hotkey in Ready panel (⌘ Command on macOS, Scroll Lock on Linux)

### Fixed
- **Double-tap bug**: Double-tap no longer triggers single-tap action

## [1.0.21] - 2025-12-31

### Added
- **Native Unicode keyboard support**: Direct Unicode input for macOS (Quartz) and Linux
- **Startup messages**: Better UX feedback during startup
- **MLX loading message**: Shows "Loading MLX (first run may take ~30s)..."

### Fixed
- **Italian accents**: Use clipboard for Unicode characters on macOS
- **MLX model name**: Correct model name for large-v3 (whisper-large-v3-mlx)

### Refactored
- Renamed ClaudeMicApp to VoxtypeApp
- Removed claude-mic references

## [1.0.20] - 2025-12-31

### Added
- **Unified installer**: Auto-platform detection for Linux/macOS
- **auto_enter default**: Now defaults to True for automatic Enter after typing
- **Alias setup instructions**: Shows at end of install

### Fixed
- **Audio device reconnection**: Improved handling of device changes
  - Force PortAudio refresh on device change
  - Recreate AudioCapture on device change
  - Retry with longer waits
  - Show device name on reconnection
- **Python compatibility**: Use Python 3.11 for MLX (torch compatibility)

## [1.0.18] - 2025-12-30

### Fixed
- **Typing stability**: Increase default typing delay to 5ms

## [1.0.17] - 2025-12-30

### Added
- **Auto-detect MLX**: Automatically use MLX on Apple Silicon Mac

## [1.0.16] - 2025-12-30

### Added
- **Keyboard mode for macOS**: Default to keyboard mode with 2ms delay
- **Typing delay**: Implement configurable typing delay for macOS

### Fixed
- **Enter key delay**: Add delay before Enter key in macOS keyboard mode

## [1.0.15] - 2025-12-30

### Fixed
- **Enter key in macOS keyboard mode**: Handle Enter key properly (fixes #16)

## [1.0.14] - 2025-12-30

### Refactored
- Simplify app.py - remove 65 lines of redundant code

## [1.0.13] - 2025-12-30

### Added
- **Modern CLI config UX**: Environment variable overrides
- **--ollama-model flag**: Switch default to qwen2.5:1.5b
- **Two-dimensional state control**: Listening mode + processing mode
- **Smart dependency check**: Shows install hints for missing dependencies

### Fixed
- **Python version**: Support 3.11-3.13 (onnxruntime compatibility)
- **Pre-load models**: Load before Ready message for better UX

### Refactored
- Simplify VAD - use Silero only via faster-whisper

## [1.0.7] - 2025-12-30

### Refactored
- Move audio warmup to beep.py for cleaner code

## [1.0.6] - 2025-12-30

### Fixed
- **Audio warmup**: Increase buffer to 500ms for better first beep

## [1.0.5] - 2025-12-30

### Fixed
- **First beep not playing**: Pre-initialize audio output at startup
  - Plays silent buffer during initialization to wake up audio system
  - Fixes issue where first LISTENING ON beep was silent
- **Beep timing**: Play beep before console output for more responsive feedback
- **Ready-to-listen beep**: Only plays after speech was ignored (not after every transcription)

## [1.0.4] - 2025-12-30

### Added
- **Busy beep feedback**: When speaking while system is transcribing, plays 5 loud beeps (900Hz)
  - Very noticeable audio feedback that speech was ignored
  - Lets user know to wait and retry
  - Respects `audio.audio_feedback` config setting
- **Ready to listen feedback**: After transcription completes in LISTENING mode
  - Plays the listening mode beep + shows "Ready to listen" in console
  - 750ms delay ensures system is truly ready before signaling

## [1.0.3] - 2025-12-30

### Added
- **Startup dependency check on Linux**: Checks if ydotoold is running before starting
  - Shows clear error message with instructions if not running
  - Also warns about missing clipboard tools (wl-copy, xclip)
- **Text injection modes documentation**: Added explanation of clipboard vs keyboard modes to README

### Fixed
- **LISTENING MODE OFF bug**: Now properly stops injecting text after exiting listening mode
- **MLX dependencies**: Fixed numba/tiktoken missing on macOS
- **Clipboard as default**: Both Linux and macOS now default to clipboard mode for reliability

### Changed
- **Code cleanup**: Prepared codebase for open source release

## [1.0.2] - 2025-12-30

### Added
- **MLX support for Apple Silicon**: `./install-macos.sh --mlx` for M1/M2/M3 Macs
  - New `mlx-whisper` backend using Metal GPU acceleration
  - 3x faster than CPU on Apple Silicon
  - New `--mlx` CLI flag to enable MLX backend
  - Updated README with macOS Quick Start section

## [1.0.1] - 2025-12-30

### Added
- **GPU installer option**: `./install.sh --gpu` installs CUDA dependencies
  - Adds `nvidia-cudnn-cu12` for GPU-accelerated transcription
  - Updated README with GPU acceleration section

## [1.0.0] - 2025-12-30

### Changed
- **Project renamed from claude-mic to voxtype**
  - New package name: `voxtype`
  - New command: `voxtype run` (was `claude-mic run`)
  - New config directory: `~/.config/voxtype/`
  - Positioned as "voice-to-text for your terminal" (not Claude-specific)

## [0.9.4] - 2025-12-30

### Added
- **audio_feedback config option**: Disable beep sounds when toggling LISTENING mode
  - New `audio.audio_feedback` setting (default: true)
  - Set to `false` in config.toml to disable beeps

## [0.9.3] - 2025-12-30

### Fixed
- **auto_enter with ydotool (keycode fix)**: Use keycode 28 instead of "enter"
  - Changed from `ydotool key enter` to `ydotool key 28:1 28:0`
  - Matches clipboard injector's Enter key handling
  - Added `auto_enter` and `enter_sent` fields to injection log

## [0.9.2] - 2025-12-30

### Fixed
- **auto_enter now works with ydotool**: Fixed Enter key not being sent
  - ydotool's `type` command doesn't interpret `\n` as Enter
  - Now sends `ydotool key enter` separately when text ends with newline
  - This fixes the `--enter` flag not working

## [0.9.1] - 2025-12-30

### Added
- **Hotkey toggle for LISTENING mode**: Press configured hotkey (e.g., ScrollLock) to toggle LISTENING mode
  - Press once to enter LISTENING mode (plays high beep)
  - Press again to exit LISTENING mode (plays low beep)
  - Works alongside voice commands ("Joshua ascolta" / "smetti")
  - Hotkey listener added to VAD mode
- `toggle_listening()` method added to LLMProcessor

## [0.9.0] - 2025-12-30

### Removed
- **Window manager feature removed**: The `target window` feature was too brittle and caused issues
  - Removed `window/` directory entirely (xdotool window manager)
  - Removed `WindowConfig` from configuration
  - Removed `TARGET_ACTIVE` and `TARGET_WINDOW` commands
  - Removed `target_active` from LLM prompt
  - This fixes the Enter key bug introduced in v0.8.16
- **Legacy command/ directory removed**: Cleanup of old command processor (replaced by llm/)

### Changed
- **Simplified LLM processor**: Reduced sanity check overrides from 8 to 3
  - Kept: Block invalid LISTENING→LISTENING transitions
  - Kept: Short exit word detection (≤4 words)
  - Kept: Inject all text in LISTENING mode if LLM says ignore
  - Removed: Multiple keyword-based overrides that didn't trust the LLM
- Architecture is now simpler and more reliable: `Audio → STT → LLM → Injector`

## [0.8.16] - 2025-12-30

### Fixed
- **Target window injection with temporary focus**: xdotool type --window doesn't work without focus
  - Now uses temporary focus: save current window → focus target → type → restore focus
  - Text now correctly arrives at target window regardless of current focus
  - Brief visual flash when switching focus is expected

## [0.8.15] - 2025-12-30

### Fixed
- **Commands in LISTENING mode for keyword fallback**: Target command now works in keyword fallback mode
  - v0.8.14 only fixed Ollama path, keyword fallback was still broken
  - Now both paths correctly recognize target command in LISTENING mode

## [0.8.14] - 2025-12-30

### Fixed
- **Commands recognized in LISTENING mode**: Target window command now works even when in LISTENING mode
  - Previously, saying "trigger + target" in LISTENING mode would inject text instead of executing command
  - Now correctly executes target_active when trigger phrase + target keywords detected

## [0.8.13] - 2025-12-30

### Fixed
- **Window manager enabled by default**: Changed `window.enabled` from `False` to `True`
  - Window manager now auto-initializes when xdotool is available
  - Target window command now works without manual configuration

## [0.8.12] - 2025-12-30

### Changed
- **Remove hardcoded trigger phrase variants**: LLM now uses phonetic similarity to recognize trigger phrase
  - Removed `TRIGGER_PHRASE_VARIANTS` dictionary
  - Prompt explains that trigger phrase may be transcribed with phonetically similar words
  - LLM handles variations intelligently instead of hardcoded list
- **Full text in logs**: Removed 100-character truncation, log now contains full text for debugging
- **Prompt fully in English**: Removed last Italian remnants ("Testo trascritto" → "Transcribed text")
- Added `target_active` command to JSON schema in prompt

## [0.8.11] - 2025-12-30

### Changed
- **Rewrite LLM prompt in English**: Prompt now focuses on semantic meaning, not exact word matching
  - Commands can arrive in ANY language
  - LLM must understand INTENT behind what user says
  - Removed Italian-specific references from prompt
  - Better multilingual support

## [0.8.10] - 2025-12-30

### Fixed
- Added `target_active` command to LLM prompt (was missing)
- Added sanity check: if LLM ignores but trigger + target keywords present, execute TARGET_ACTIVE

## [0.8.9] - 2025-12-30

### Fixed
- Block invalid state transitions: cannot re-enter LISTENING when already in LISTENING mode
- LLM now correctly handles state machine transitions

## [0.8.8] - 2025-12-30

### Added
- **TARGET_ACTIVE voice command**: Say "Joshua, questa finestra" to set currently focused window as target
- Added sanity check: block state changes without trigger phrase in IDLE mode

## [0.8.7] - 2025-12-30

### Added
- **Window targeting (Issue #11)**: Send text to specific window without changing focus
  - Connect XdotoolWindowManager to text injection
  - Text is sent via xdotool `type --window` when target is set

## [0.8.6] - 2025-12-30

### Added
- Enhanced `llm_decision` logging: include `current_state` in every log entry
- Ollama timeout/error info now included in `override_reason`

## [0.8.5] - 2025-12-30

### Fixed
- "ascolta Joshua" now triggers LISTENING mode (keyword order was wrong)
- Check for enter keywords ANYWHERE in text, not just after trigger

## [0.8.4] - 2025-12-30

### Fixed
- Restored exit word detection for short phrases (≤4 words) in LISTENING mode
- "Joshua stop" no longer enters LISTENING mode from IDLE (exit words blocked in IDLE)

## [0.8.3] - 2025-12-30

### Added
- Enhanced LLMResponse with debug fields: `backend`, `override_reason`, `raw_llm_response`
- Full debug info in `llm_decision` log entries

## [0.8.2] - 2025-12-30

### Fixed
- Removed aggressive keyword overrides that caused incorrect LLM behavior
- Trust LLM decisions more, reduce keyword-based overrides

## [0.8.1] - 2025-12-30

### Added
- **Enhanced session_start logging**: Log all startup parameters for debugging
  - input_mode, trigger_phrase, stt_model, stt_device, stt_language
  - output_mode, auto_enter, debug, silence_ms
  - Version included in every session_start event
- Added `debug-session*.jsonl` to `.gitignore`

### Fixed
- Every code change now bumps version (PATCH) for proper tracking

## [0.8.0] - 2025-12-30

### Changed
- **LLM-first architecture**: Complete refactoring of command processing
  - ALL transcribed text now goes through LLM for decision-making
  - LLM decides: ignore, inject text, change state, or execute command
  - Trigger phrase (formerly "wake word") can now appear ANYWHERE in the sentence
  - Better recognition of command variants (e.g., "zmetti" recognized as "smetti")
  - Unified processing: no more separate wake word check + command processor

### Added
- New `src/claude_mic/llm/` module:
  - `models.py`: LLMRequest, LLMResponse, Action, AppState, Command
  - `prompts.py`: System prompt for Ollama, fallback keywords
  - `processor.py`: Unified LLMProcessor with Ollama + keyword fallback
- Log `llm_decision` events in JSONL for debugging

### Removed
- Old `_check_wake_word()` method (replaced by LLM)
- Old `_listening_mode` flag (LLMProcessor tracks state internally)
- Hardcoded exit word matching (LLM handles this now)

## [0.7.2] - 2025-12-30

### Added
- **JSONL structured logging**: `--log-file` option for machine-readable logs
  - Log transcriptions, wake word checks, commands, state changes, injections, VAD events
  - JSONL format (one JSON object per line) for easy parsing
  - Example: `claude-mic run --vad --wake-word Joshua --log-file session.jsonl`
- **Audio feedback**: Beep sounds when entering/exiting LISTENING mode
  - High pitch (800Hz) beep on enter
  - Low pitch (400Hz) beep on exit

## [0.7.1] - 2025-12-30

### Fixed
- LISTENING mode exit: "Smetti!", "Smetti.", "basta" now work correctly
  - Handle punctuation (!, .) after exit words
  - "Joshua basta" now triggers exit (was only checking smetti/stop)
- Added Whisper transcription error variants: zmetti, zmeti, smetty, smety

## [0.7.0] - 2025-12-30

### Added
- **Voice command system**: Intelligent command processing with Ollama LLM
  - Commands: ascolta (listening mode), smetti (stop), incolla (paste), annulla (undo), ripeti (repeat)
  - Keyword-based fallback when Ollama unavailable
- **LISTENING mode**: Say "Joshua, ascolta" to enter continuous transcription (no wake word needed)
  - Exit with "smetti" or "Joshua, smetti"
- **Target window support**: `--target-window` option for X11 (xdotool)
  - Send text to specific window without focus
- **CommandConfig**: New config section for voice commands
- **WindowConfig**: New config section for target window

### Fixed
- Wake word detection: added `?` as separator (Whisper often uses `Joshua?`)

## [0.6.1] - 2025-12-30

### Fixed
- Wake word detection: added period (`.`) as separator (Whisper sometimes adds periods)
- Enhanced debug logging in `_check_wake_word()` to diagnose wake word issues
  - Shows exact text received from transcription
  - Shows which separator matched
  - Helps identify why wake word might not be detected

## [0.6.0] - 2025-12-30

### Added
- **Wake word support**: `--wake-word` option to activate only with keyword
  - Example: `claude-mic run --vad --wake-word Joshua`
  - Text after wake word is extracted and typed
  - Supports various formats: "Joshua, ...", "Joshua:", "Joshua ..."
- **Debug mode**: `--debug` flag shows all transcriptions even without wake word
- Feedback message when wake word not detected

## [0.5.0] - 2025-12-30

### Added
- **VAD mode**: `--vad` flag for hands-free voice activity detection
  - Uses Silero VAD bundled with faster-whisper
  - No push-to-talk key needed, auto-detects speech
- **Silence threshold**: `--silence-ms` option (default 1200ms)
- TTS support: `claude-mic speak "text"` command with espeak-ng

## [0.4.4] - 2025-12-30

### Fixed
- CUDA library loading: preload cuDNN/cuBLAS with ctypes before ctranslate2

## [0.4.1] - 2025-12-30

### Added
- **GPU support**: `--gpu` flag to use CUDA for faster transcription
  - Automatically sets compute_type to float16 for optimal GPU performance
  - Displays "GPU (CUDA)" in the status panel when enabled

## [0.4.0] - 2025-12-30

### Added
- **Clipboard mode**: `--clipboard` flag for text with accented characters
  - Uses Ctrl+Shift+V for terminal paste (instead of Ctrl+V for images)
  - Auto-paste enabled by default with `auto_paste` config option
  - Sends Enter key separately after paste when `auto_enter` is enabled

### Fixed
- ydotool typing speed increased (1ms delay, was 20ms)
- Enter key now works correctly in clipboard mode (200ms delay after paste)

### Changed
- Removed auto-fallback to clipboard for non-ASCII text (now explicit with --clipboard)

## [0.3.0] - 2025-12-29

### Added
- **macOS support**: Full support for macOS with pynput + osascript
  - `install-macos.sh` installer script
  - `MacOSInjector` using osascript for text injection
  - Detailed Accessibility permission instructions (Italian)
  - Alternative key suggestions for Mac (F5, F6, Right Command)
- Right Option (`KEY_RIGHTALT`) and Left Option (`KEY_LEFTALT`) key mappings

### Fixed
- Improved macOS Accessibility instructions with step-by-step guide
- Added suggested hotkeys for Mac keyboards (no ScrollLock)

## [0.2.0] - 2025-12-29

### Added
- `--enter` flag to auto-press Enter after typing
- `injection.auto_enter` config option
- "Ready!" message after initialization completes

### Fixed
- ydotool virtual keyboard no longer detected as input device
- X11/Wayland clipboard detection now uses XDG_SESSION_TYPE correctly
- udev rule for /dev/uinput added to setup-permissions.sh

## [0.1.2] - 2025-12-29

### Added
- **One-command install**: `./install.sh` builds and sets up everything
- **User-level install**: Default install to `~/.local/bin`, no sudo needed
- **Separate permissions script**: `setup-permissions.sh` (4 lines, easy to review)
- **Uninstall script**: `./uninstall.sh` cleans up everything
- **Systemd user service**: ydotoold runs as user service, not system

### Changed
- Simplified README to minimal quick-start guide
- `--system` flag for system-wide install when needed

## [0.1.1] - 2025-12-29

### Added
- **Docker build scripts**: Build ydotool and evdev without polluting host system
  - `build/build-ydotool.sh` - Builds ydotool v1.0.4 from source
  - `build/build-evdev.sh` - Builds evdev wheel without requiring python3-dev
- **Dockerfile.ydotool**: Multi-stage build for ydotool binaries
- **Dockerfile.evdev**: Multi-stage build for evdev Python wheel

### Changed
- Updated README with Docker-based installation instructions
- No longer requires `python3-dev` or `ydotool` system package

## [0.1.0] - 2025-12-29

### Added
- Initial implementation of claude-mic
- **CLI commands**: `run`, `check`, `init`, `config`
- **Audio capture**: Using sounddevice with callback-based streaming
- **Speech-to-text**: faster-whisper integration with model selection (tiny/base/small/medium/large-v3)
- **Hotkey detection**:
  - evdev listener for Linux (works on X11, Wayland, console)
  - pynput fallback for macOS and X11
  - Smart key detection with fallback suggestions
- **Text injection**:
  - ydotool (Linux universal)
  - wtype (Wayland)
  - xdotool (X11)
  - clipboard fallback
- **Configuration**: TOML config with Pydantic validation
- **Dependency checker**: `claude-mic check` command
- **Multi-language support**: Auto-detection via Whisper
- **VAD stub**: Interface ready for future Silero VAD integration

### Technical Details
- Push-to-talk mode with configurable hotkey (default: ScrollLock)
- State machine: IDLE → RECORDING → TRANSCRIBING → INJECTING
- Graceful degradation when tools are missing
- Clear error messages with remediation steps
