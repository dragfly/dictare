# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.60.0-alpha] - 2026-01-29

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
