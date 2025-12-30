# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
