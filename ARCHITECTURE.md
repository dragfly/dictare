# Architecture

## Overview

`voxtype` is a voice-to-text tool for terminals. It uses VAD (Voice Activity Detection) for hands-free speech detection.

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Hotkey    │───>│   Audio     │───>│    STT      │───>│  Injector   │
│  Listener   │    │  Capture    │    │  (Whisper)  │    │  (Typing)   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
      │                  │                                      │
      │            ┌─────────────┐                              │
      │            │  Silero VAD │                              │
      │            └─────────────┘                              │
      └──────────────────── State Machine ──────────────────────┘
```

**Flow:**
1. **Tap hotkey** → Toggle listening on/off
2. **Speak** → Silero VAD detects speech, audio captured
3. **Pause** → VAD detects silence, audio sent to Whisper
4. **Transcribe** → Text typed into active window

**Double-tap hotkey** → Switch between transcription and command modes.

## Key Design Decisions

### 1. Offline-First

All transcription happens locally using [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CPU/CUDA) or [mlx-whisper](https://github.com/ml-explore/mlx-examples) (Apple Silicon). No internet required.

### 2. Platform-Specific Backends

Each platform uses native, reliable backends:

```
src/voxtype/
├── hotkey/
│   ├── evdev_listener.py    # Linux (uinput)
│   └── pynput_listener.py   # macOS (Accessibility API)
├── audio/
│   ├── capture.py           # sounddevice
│   └── vad.py               # Silero VAD
├── stt/
│   ├── faster_whisper.py    # CPU/CUDA
│   └── mlx_whisper.py       # Apple Silicon
├── injection/
│   ├── ydotool.py           # Linux (uinput)
│   ├── quartz.py            # macOS (Quartz, Unicode)
│   └── file.py              # Agent mode (inputmux)
└── core/
    └── app.py               # Orchestrator
```

### 3. No Fallbacks

Each platform has one canonical backend. If it's not available, voxtype fails with a clear error message explaining how to fix it:

- **Linux**: Requires `ydotoold` running
- **macOS**: Requires Accessibility permission

## Speech-to-Text Models

| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| `tiny` | 75 MB | Fastest | Basic |
| `base` | 150 MB | Fast | Good |
| `small` | 500 MB | Medium | Better |
| `medium` | 1.5 GB | Slower | Great |
| `large-v3-turbo` | 1.6 GB | Medium | **Default** |
| `large-v3` | 3 GB | Slowest | Best |

GPU auto-detection:
- macOS (Apple Silicon): MLX
- Linux (NVIDIA): CUDA

## Platform Details

### Linux

**Hotkey** (evdev): Reads `/dev/input/event*` directly. Requires `input` group membership.

**Injection** (ydotool): Uses `/dev/uinput` to simulate keyboard. Requires `ydotoold` daemon.

Both work on X11, Wayland, and TTY.

### macOS

**Hotkey** (pynput): Uses Accessibility APIs. Requires terminal in Accessibility list.

**Injection** (Quartz): Uses CGEventCreateKeyboardEvent. Full Unicode support.

## Configuration

Config file: `~/.config/voxtype/config.toml`

```toml
[stt]
model = "large-v3-turbo"
language = "auto"

[hotkey]
key = "KEY_SCROLLLOCK"   # Linux
# key = "KEY_RIGHTMETA"  # macOS (Right Command)

[audio]
audio_feedback = true
```

See `voxtype run --help` for all options.
