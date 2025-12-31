# Architecture

## Overview

`voxtype` is a voice-to-text tool designed for terminal applications. It supports two input modes:
- **VAD mode** (default): Hands-free, automatic speech detection using Silero VAD
- **Push-to-talk mode**: Hold a hotkey to record, release to transcribe

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Hotkey    │───>│   Audio     │───>│    STT      │───>│  Injector   │
│  Listener   │    │  Capture    │    │  (Whisper)  │    │  (Typing)   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
      │                  │                                      │
      │            ┌─────────────┐                              │
      │            │  Silero VAD │ (in VAD mode)                │
      │            └─────────────┘                              │
      └──────────────────── State Machine ──────────────────────┘
                    IDLE → RECORDING → TRANSCRIBING → INJECTING
```

## Key Design Decisions

### 1. Offline-First

All transcription happens locally using [faster-whisper](https://github.com/SYSTRAN/faster-whisper), a CTranslate2-optimized implementation of OpenAI's Whisper. No internet connection required, no API keys, no usage limits.

### 2. Input Modes

**VAD mode** (default):
- Uses Silero VAD for speech detection
- Hotkey toggles listening on/off
- Speech automatically detected and transcribed
- Double-tap hotkey to switch between transcription/command modes

**Push-to-talk mode** (`--ptt`):
- Hold key → Start recording
- Release key → Stop recording, transcribe, type
- Simpler, more predictable, avoids false activations

### 3. Modular Components

Each component has an abstract base class and multiple implementations:

```
src/voxtype/
├── hotkey/
│   ├── base.py              # Abstract HotkeyListener
│   ├── evdev_listener.py    # Linux (works everywhere)
│   └── pynput_listener.py   # macOS, X11 fallback
├── audio/
│   ├── capture.py           # sounddevice-based recording
│   ├── vad.py               # Silero VAD for speech detection
│   └── beep.py              # Audio feedback (beeps, TTS)
├── stt/
│   ├── base.py              # Abstract STTEngine
│   ├── faster_whisper.py    # Local Whisper (CPU/CUDA)
│   └── mlx_whisper.py       # Apple Silicon MLX
├── injection/
│   ├── base.py              # Abstract TextInjector
│   ├── ydotool.py           # Linux universal
│   ├── wtype.py             # Wayland
│   ├── xdotool.py           # X11
│   ├── macos.py             # macOS (osascript)
│   ├── quartz.py            # macOS (Quartz, Unicode)
│   └── clipboard.py         # Fallback
├── llm/
│   ├── processor.py         # LLM command processing
│   ├── models.py            # Data models (AppState, Command, etc.)
│   └── prompts.py           # LLM prompts
└── core/
    ├── app.py               # Orchestrator
    └── state.py             # AppState, ProcessingMode enums
```

### 4. Graceful Degradation

If the preferred tool isn't available, fall back to the next best option:

**Hotkey detection:**
- Linux: evdev → pynput
- macOS: pynput only

**Text injection:**
- Linux: ydotool → wtype → xdotool → clipboard
- macOS: osascript → clipboard

## Speech-to-Text Models

We use OpenAI's Whisper via `faster-whisper` (CPU/CUDA) or `mlx-whisper` (Apple Silicon). Models are downloaded automatically on first use.

| Model | Size | RAM | Speed (GPU) | Quality |
|-------|------|-----|-------------|---------|
| `tiny` | 75 MB | ~1 GB | ~0.5s | Good for clear speech |
| `base` | 150 MB | ~1 GB | ~1s | Balanced |
| `small` | 500 MB | ~2 GB | ~2s | Better accuracy |
| `medium` | 1.5 GB | ~4 GB | ~4s | Best for non-English |
| `large-v3` | 3 GB | ~6 GB | ~8s | Maximum accuracy |
| `large-v3-turbo` | 1.6 GB | ~4 GB | ~3s | **Default**, fast + accurate |

**GPU auto-detection:**
- macOS (Apple Silicon): MLX is auto-detected
- Linux (NVIDIA): CUDA is auto-detected

## Platform-Specific Details

### Linux

**Hotkey Detection (evdev):**
- Reads directly from `/dev/input/event*` devices
- Requires user in `input` group
- Works on X11, Wayland, and TTY

**Text Injection (ydotool):**
- Uses `/dev/uinput` to simulate keyboard
- Requires `ydotoold` daemon running
- Universal - works on X11, Wayland, TTY

### macOS

**Hotkey Detection (pynput):**
- Uses macOS accessibility APIs
- Requires Accessibility permission for terminal app

**Text Injection (osascript):**
- Uses AppleScript `keystroke` command
- Also requires Accessibility permission

**Recommended hotkeys** (don't produce terminal escape sequences):
- `KEY_RIGHTMETA` - Right Command (⌘)
- `KEY_RIGHTALT` - Right Option (⌥)

## Data Flow

1. **Hotkey pressed** → State changes to RECORDING
2. **Audio capture** → Samples buffered in memory (16kHz, mono, float32)
3. **Hotkey released** → State changes to TRANSCRIBING
4. **Whisper inference** → Audio → text (runs on CPU or GPU if available)
5. **Text injection** → Simulated keystrokes typed into active window
6. **State returns to IDLE**

## Configuration

Config file: `~/.config/voxtype/config.toml`

```toml
[stt]
model_size = "large-v3-turbo"  # tiny, base, small, medium, large-v3, large-v3-turbo
language = "auto"              # or specific: "en", "it", "es", etc.

[hotkey]
key = "KEY_SCROLLLOCK"   # Linux default
# key = "KEY_RIGHTMETA"  # macOS recommended

[injection]
auto_enter = true        # Press Enter after typing (default)

[audio]
audio_feedback = true    # Beeps and TTS for mode changes
```

## Dependencies

**Python packages:**
- `faster-whisper` - Speech-to-text engine
- `sounddevice` - Audio capture
- `numpy` - Audio buffer handling
- `typer` + `rich` - CLI framework
- `pydantic` - Config validation

**Platform-specific:**
- Linux: `evdev` (hotkey), `ydotool` (typing)
- macOS: `pynput` (hotkey), `osascript` (typing, built-in)

## Future Enhancements

- **Cloud STT**: Optional OpenAI Whisper API for faster/better transcription
- **Custom vocabulary**: Boost recognition of technical terms
- **Streaming transcription**: Real-time partial results during speech
