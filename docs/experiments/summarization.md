# Experiment: Voice-to-Summary

**Status:** Concept / pre-implementation
**Category:** Output pipeline extension

---

## The Problem

Dictare's current model is **speak → transcribe → submit**. Every utterance goes directly to the output target (agent PTY or keyboard). This works well for short, precise commands but breaks down when:

- You speak conversationally (fragmented sentences, corrections, digressions)
- You want to compose a longer message before sending (email, form field, WhatsApp message)
- The output target is not an AI agent that can interpret messy voice input

---

## The Idea

Add a **collect → summarize → review → submit** flow:

1. **Collect**: utterances accumulate in a local buffer instead of being sent immediately
2. **Summarize**: at a trigger (voice command, hotkey, or silence threshold), an LLM summarizes the buffer into coherent prose
3. **Review**: dictare reads back the summary via TTS — user can accept, re-record, or edit
4. **Submit**: the summary goes to the output target

---

## Use Cases

### 1. Message composition
> "Send Marco a voice message... ok so I wanted to tell him that... the meeting is moved to Thursday... no wait, Friday... actually Thursday at 4pm"

→ buffer → summarize → TTS reads: *"Hey Marco, the meeting has been moved to Thursday at 4pm."* → submit to WhatsApp/Telegram/email

### 2. Form field dictation
> "Description of the issue: so basically I was on the homepage and then I clicked the button and it crashed and then I tried again and it crashed again"

→ summarize → *"The app crashes consistently when clicking the button on the homepage."* → paste into form field

### 3. Pre-processing before agent submission
Useful when the output target is **not** an AI (e.g., Word, a form, a dumb terminal). The summary step adds the intelligence that the target lacks.

### 4. Meeting/thinking notes
Long voice dumps → structured summary → saved to file or clipboard.

---

## Architecture Sketch

```
[mic] → [STT] → [utterance buffer]
                      |
               [trigger: hotkey / "ok send" / silence_ms]
                      |
               [summarization agent]
                    /         \
             [local LLM]   [remote LLM]
             (mlx/ollama)  (claude/openai)
                      |
               [TTS readback] ← optional
                      |
               [user: accept/retry/edit]
                      |
               [output target]
```

---

## OpenVIP Protocol Extension (future)

The summarization step could become a first-class OpenVIP service:

```
POST /summarize
{
  "utterances": [...],       // array of transcription segments
  "target_length": "short",  // short | medium | long
  "style": "message"         // message | bullet | formal
}
→ { "text": "...", "confidence": 0.9 }
```

This lets any OpenVIP-compatible agent decide whether to use local or remote summarization, and lets dictare provide it as a default built-in service — just as it provides STT and TTS.

---

## Trigger Mechanisms

| Trigger | Mechanism |
|---|---|
| Voice command | "ok send", "summarize", "done" — detected by keyword spotting or STT pattern match |
| Hotkey | Second configurable hotkey (e.g., right Cmd again, or dedicated key) |
| Silence threshold | Extended silence (e.g., 5s) in collect mode |
| Manual | UI button in the web interface |

---

## Key Open Questions

1. **Collect mode activation**: how does the user enter collect mode vs direct-submit mode? Separate hotkey? Config toggle?
2. **Buffer persistence**: if the engine restarts mid-collection, is the buffer lost?
3. **Summarization model**: local (latency ~1s on M-series, private) vs remote (better quality, needs API key)
4. **Review UX**: TTS readback is optional — should it be on by default? What if TTS is disabled?
5. **Edit flow**: if user wants to correct the summary, do they re-dictate or type?

---

## Why This Matters for Dictare's Positioning

Current dictare: voice layer for **AI coding agents** (Claude Code, Cursor, Aider) — the agent itself handles messy input.

With summarization: dictare becomes a voice layer for **any software**, including dumb targets. This massively expands the addressable use case without changing the core architecture.
