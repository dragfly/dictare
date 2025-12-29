# Architecture

## Overview

`claude-mic` is a push-to-talk voice-to-text tool designed for terminal applications. It captures audio while a hotkey is held, transcribes it locally using Whisper, and types the result into the active window.

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Hotkey    │───>│   Audio     │───>│    STT      │───>│  Injector   │
│  Listener   │    │  Capture    │    │  (Whisper)  │    │  (Typing)   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
      │                                                         │
      └──────────────────── State Machine ──────────────────────┘
                    IDLE → RECORDING → TRANSCRIBING → TYPING
```

## Key Design Decisions

### 1. Offline-First

All transcription happens locally using [faster-whisper](https://github.com/SYSTRAN/faster-whisper), a CTranslate2-optimized implementation of OpenAI's Whisper. No internet connection required, no API keys, no usage limits.

### 2. Push-to-Talk

Instead of always-listening with Voice Activity Detection (VAD), we use a simple push-to-talk model:
- **Hold key** → Start recording
- **Release key** → Stop recording, transcribe, type

This is simpler, more predictable, and avoids false activations.

### 3. Modular Components

Each component has an abstract base class and multiple implementations:

```
src/claude_mic/
├── hotkey/
│   ├── base.py              # Abstract HotkeyListener
│   ├── evdev_listener.py    # Linux (works everywhere)
│   └── pynput_listener.py   # macOS, X11 fallback
├── audio/
│   ├── capture.py           # sounddevice-based recording
│   └── vad.py               # (stub for future VAD)
├── stt/
│   ├── base.py              # Abstract STTEngine
│   └── faster_whisper.py    # Local Whisper
├── injection/
│   ├── base.py              # Abstract TextInjector
│   ├── ydotool.py           # Linux universal
│   ├── wtype.py             # Wayland
│   ├── xdotool.py           # X11
│   ├── macos.py             # macOS (osascript)
│   └── clipboard.py         # Fallback
└── core/
    └── app.py               # Orchestrator
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

We use OpenAI's Whisper via `faster-whisper`. Models are downloaded automatically on first use.

| Model | Size | RAM | Speed | Quality |
|-------|------|-----|-------|---------|
| `tiny` | 75 MB | ~1 GB | ~1s | Good for clear speech |
| `base` | 150 MB | ~1 GB | ~2s | Default, balanced |
| `small` | 500 MB | ~2 GB | ~4s | Better accuracy |
| `medium` | 1.5 GB | ~4 GB | ~8s | Best for non-English |
| `large-v3` | 3 GB | ~6 GB | ~15s | Maximum accuracy |

**Recommendation:**
- English: `base` or `small`
- Other languages: `medium` (much better for Italian, Spanish, etc.)

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

Config file: `~/.config/claude-mic/config.toml`

```toml
[stt]
model_size = "medium"    # tiny, base, small, medium, large-v3
language = "auto"        # or specific: "en", "it", "es", etc.

[hotkey]
key = "KEY_SCROLLLOCK"   # Linux default
# key = "KEY_RIGHTMETA"  # macOS recommended

[injection]
auto_enter = false       # Press Enter after typing
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

- **VAD mode**: Always-listening with Silero VAD (interface ready in `audio/vad.py`)
- **Cloud STT**: Optional OpenAI Whisper API for faster/better transcription
- **Custom vocabulary**: Boost recognition of technical terms
