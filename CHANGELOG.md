# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0b141] - 2026-02-19

### Changed

- Settings UI: Audio page now shows only the commonly-changed fields in the
  form (audio_feedback, silence_ms, headphones_mode, max_duration).
  Advanced fine-tuning fields (sample_rate, channels, device, pre_buffer_ms,
  min_speech_ms, transcribing_sound_min_ms) are hidden from the form and
  accessible only via `voxtype config edit` or the config.toml directly.
- The Sounds TOML editor template now includes a note pointing to the
  advanced [audio] parameters and how to edit them.
- Introduced `HIDDEN_FORM_KEYS` in field-config.ts: a single place to move
  any field between the form UI and TOML-only access.

## [0.1.0b140] - 2026-02-19

### Added

- `audio.transcribing_sound_min_ms` config field (default: 8000 ms): controls the
  minimum audio duration before the typewriter sound plays during transcription.
  Previously hardcoded at 8 s; now visible and adjustable in Settings → Audio → SOUNDS.

### Fixed

- Agent index switching: `app/controller.py` was subtracting 1 from the index
  before passing it to engine, which also subtracts 1 — double offset caused
  index 1 to resolve as -1 (always fail).
- `tts/outetts.py` had a private `_is_apple_silicon()` duplicating `utils/hardware.py`.
  Now imports `is_apple_silicon` from hardware module.

### Removed

- Partial/realtime transcription scaffolding (`_realtime`, `_partial_*` fields,
  worker thread, `realtime_model` config). The implementation was incomplete —
  partial text was computed but never sent anywhere. Concept parked in
  `docs/notes/realtime-partial-transcription.md`.
- `create_partial()`, `create_status()`, `create_error()` from `openvip_messages.py`:
  defined but never called in production code. `create_message(partial=True)` still
  works for when partial transcription is properly implemented.
- `realtime` parameter from `create_engine()` and `VoxtypeEngine.__init__()`.
- `cli/models.py` references to removed `realtime_model` and `qwen3` engine.

## [0.1.0b139] - 2026-02-19

### Removed

- `qwen3` TTS engine: it was an LLM (Qwen3), not a TTS engine — deleted `tts/qwen3.py`,
  removed from `TTSConfig.engine` Literal, `tts/__init__.py`, `install_info.py`, and `speak.py`.
- Dead TTS phrase keys from `engine.py`: `transcription_mode`, `command_mode`, `voice` —
  superseded by the pipeline architecture. Only `agent` phrase remains.
- `daemon.preload_tts`, `daemon.preload_stt`, `daemon.idle_timeout` config fields: never
  read anywhere in the codebase; removed from `DaemonConfig` and config template.
- `src/voxtype/ui/__init__.py`: phantom package (0 bytes, no imports, no purpose).
- Added `docs/notes/plugin-filter-llm-vision.md`: architecture vision for plugin/filter/LLM
  integration (four model categories: STT, TTS, LLM, Translation).

## [0.1.0b138] - 2026-02-19

### Changed

- TOML editor: full WYSIWYG + validation redesign.
  - **Fetch**: reads the raw section text from the config file verbatim (line-based
    scanner). User comments, blank lines, and formatting are preserved exactly.
    Falls back to a comment-only template when the section is absent from the file.
  - **Save**: validates structure with Pydantic (fields, types), then writes the
    user's literal text to the config file — the model is never used to regenerate
    the stored text.
  - Previous behaviour regenerated the TOML from the Pydantic model on every save,
    discarding user comments and reformatting values.

## [0.1.0b137] - 2026-02-19

### Fixed

- TOML editor (agent_types section): `continue_args` was silently stripped on save/reload.
  Both `_serialize_agent_types` and `_apply_agent_types` now handle `continue_args`.
- TOML editor: agent type names containing dots are now quoted in the serialized output
  (`[agent_types."sonnet-4.6"]` instead of `[agent_types.sonnet-4.6]`).
- Updated `_AGENT_TYPES_HEADER` comment to document `continue_args` syntax.

## [0.1.0b136] - 2026-02-19

### Added

- `AgentTypeConfig.continue_args`: optional list of args inserted after `argv[0]` when
  `--continue` / `-C` is passed to `voxtype agent`. Keeps continue syntax inside the
  agent type config (Claude uses `["-c"]`, Codex could use `["--resume"]`, etc.).
- `voxtype agent <name> --type <type> --continue` / `-C` flag: continues the previous
  session using the type's `continue_args`. If `continue_args` is empty, a warning is
  printed and the agent runs normally. Silently ignored when using `--` command override.

## [0.1.0b135] - 2026-02-19

### Fixed

- PTYSession: resolve agent binary with `shutil.which()` before fork — if the command
  is not found or the resolved path no longer exists (e.g. Homebrew Cask updated and old
  version removed), raises `FileNotFoundError` with a clear message instead of a cryptic
  `ENOENT posix_spawn` from inside the child process.

## [0.1.0b134] - 2026-02-19

### Fixed

- Config: agent type names containing dots now use correct TOML quoted-key syntax in
  examples (`[agent_types."sonnet-4.6"]` not `[agent_types.sonnet-4.6]`). Unquoted dot
  keys in TOML are parsed as nested tables, causing pydantic `command field required` error.
- Config: updated agent_types comment to document the `voxtype agent <name> --type <type>`
  syntax and the fact that multiple sessions can share the same agent type.
- UI: `--destructive` CSS color raised from lightness 30% to 62% — error messages in the
  TOML editor were dark red on dark background (unreadable).

## [0.1.0b133] - 2026-02-18

### Fixed

- Reverted `requires-python` back to `>=3.11,<3.12`: `mlx-whisper` pulls in `torch==2.0.1`
  which only has `cp311` wheels — Python 3.12 breaks `--extra mlx`. Added comment in
  `pyproject.toml` explaining the reason so this is not accidentally changed again.
  To unblock 3.12, upgrade torch to >=2.1 in the mlx extra first.

## [0.1.0b132] - 2026-02-18

### Fixed

- Audio: carriage-return (ready) sound is now gated by the same 8-second threshold as the
  typewriter loop — no more carriage-return sound for short recordings that never triggered
  typewriter feedback. `was_looping` is captured before `stop_loop()` and used to
  conditionally suppress the ready sound.

## [0.1.0b131] - 2026-02-18

### Fixed

- Linux: `linux-install.sh` now installs `gir1.2-ayatanaappindicator3-0.1` on Ubuntu 22.04+
  (old name `gir1.2-appindicator3-0.1` no longer exists), fixing tray icon on modern Ubuntu.
- Linux: `linux-install.sh` installs udev rule `99-voxtype.rules` for evdev access —
  hotkey (ScrollLock) now works immediately without adding user to `input` group or re-logging in.
- Linux: `GI_TYPELIB_PATH` in the generated systemd unit is now architecture-aware —
  ARM64 uses `aarch64-linux-gnu`, ARMv7 uses `arm-linux-gnueabihf`, x86_64 unchanged.
- `pyproject.toml`: relaxed `requires-python` from `>=3.11,<3.12` to `>=3.11,<3.13`,
  unblocking users on Python 3.12 (Ubuntu 24.04, Fedora 41 default).

## [0.1.0b124] - 2026-02-18

### Fixed

- TOML editor: fix syntax highlight colors — switched to `classHighlighter` + scoped
  `EditorView.theme` (higher CSS specificity), removing `defaultHighlightStyle` entirely.
  Comments now green (`#6a9955`), section headers yellow (`#dcd43a`), all other tokens
  (strings, numbers, booleans) plain text color.

## [0.1.0b123] - 2026-02-18

### Changed

- `voxtype agent`: agent_id (session name) is now independent from the agent type.
  Added `--type <type>` option to select the command template from `agent_types` config.
  Without `--type`, `default_agent_type` is used. agent_id is required.
  Examples: `voxtype agent frontend --type claude-sonnet`, `voxtype agent frontend`
- Tests: added `TestAgentCLIContract` — 7 end-to-end CLI tests verifying name is
  required, `--type` selects command, default fallback, and session name independence.

## [0.1.0b122] - 2026-02-18

### Changed

- TOML editor: replaced `basicSetup` with `minimalSetup` + custom `HighlightStyle` —
  comments green (`#6a9955`), section headers yellow (`#dcd43a`), all other tokens
  (strings, numbers, booleans) plain text color.

## [0.1.0b121] - 2026-02-18

### Changed

- `toml_sections.py`: replaced 3 bespoke serialize/apply function pairs with generic
  `_serialize_pydantic_section` / `_apply_pydantic_section` helpers + `_GENERIC_SECTIONS`
  registry. `agent_types` and `keyboard.shortcuts` remain special cases. ~90 lines → ~45.

## [0.1.0b120] - 2026-02-18

### Fixed

- SettingsNav: `effect_update_depth_exceeded` crash when expanding Keyboard/Advanced
  — `$effect` read `expanded` via spread, causing a reactive loop. Fixed with `untrack()`.

### Added

- TOML editor support for `audio.sounds`, `pipeline.submit_filter`, `pipeline.agent_filter`
  (backend serialize/apply + frontend widget)
- Size hints for previously unsized string fields: `audio.device`, `stt.hotwords`,
  `tts.voice`, `logging.log_file`, `daemon.socket_path`
- ui-hints.json regenerated; `pipeline.submit_filter.triggers` removed as standalone key

## [0.1.0b119] - 2026-02-18

### Changed

- Settings UI regenerated from `_future/ui-schema/` generator (v0.2.0):
  - `field-config.ts`: now includes `TOML_EDITABLE_KEYS` (generated, not hand-written)
  - `tabs.ts`: normalized to canonical inline format for children objects
- `_future/ui-schema/` generator: `widget: "toml"`, `children` nav, `README.md`

## [0.1.0b118] - 2026-02-18

### Changed

- **Settings UI — breathing room** — increased top padding in content area and sidebar brand, matching Claude's visual rhythm. Section title larger (text-xl).

## [0.1.0b117] - 2026-02-18

### Changed

- **Settings UI — hierarchical nav** — expandable sections in the left sidebar. "Keyboard" expands to Hotkey + Shortcuts; "Advanced" expands to Client, Logging, Statistics, Daemon, Pipeline. Each sub-item shows only its focused content on the right. Removed accordion from the content area.

## [0.1.0b116] - 2026-02-18

### Changed

- **Settings UI — inline descriptions** — field descriptions are now always visible below the field name, matching Claude and ChatGPT UX patterns. Removed the tooltip ⓘ icon.

## [0.1.0b115] - 2026-02-18

### Changed

- **Settings UI — accordion groups** — tabs with sub-sections (Advanced, Hotkey) now use collapsible accordion panels instead of a single long scrolling page. Each group shows a field count and expands on click.

## [0.1.0b114] - 2026-02-18

### Fixed

- **Agents tab empty** — `agent_types` was excluded from `list_config_keys()` so the Agents tab showed "No configurable fields". Now exposed as a `dict` field so the TOML editor renders correctly.

## [0.1.0b113] - 2026-02-18

### Changed

- **Settings UI — non-default field indicator** — fields with a saved value different from the schema default now show an amber label and a small dot, making customizations immediately visible.
- **Settings UI — string field placeholders** — string fields show their default value as placeholder text when empty, reducing cognitive load.

## [0.1.0b112] - 2026-02-18

### Added

- **Agent type presets** — renamed `[agents.*]` → `[agent_types.*]` in config for clarity. Added `default_agent_type` field so `voxtype agent` with no arguments launches the default agent. Added optional `description` field to each agent type.
- **TOML textarea editor in settings UI** — complex config sections (`agent_types`, `keyboard.shortcuts`) now display a CodeMirror-powered TOML editor with syntax highlighting instead of "Edit in config.toml". Server-side validation via Pydantic before saving.
- **Agents tab in settings UI** — dedicated tab for agent type presets with TOML editor including commented examples.
- **Shortcuts tab in Hotkey settings** — `keyboard.shortcuts` now visible in the UI via TOML editor (previously hidden).
- **New API endpoints** — `GET /settings/toml-section/{section}` and `POST /settings/toml-section/{section}` for reading/writing complex config sections.

## [0.1.0b111] - 2026-02-18

### Fixed

- **Agent "standby" despite engine "listening"** — When saved state has `__keyboard__` as active agent, first SSE agent now correctly becomes current in agents mode. Added regression test.
- **Linux tray icon fallback** — Monkey-patch pystray to save icons with `.png` extension, fixing AppIndicator falling back to theme icons instead of displaying custom microphone icons.

## [0.1.0b110] - 2026-02-17

### Fixed

- **Linux install script** — PyGObject installed AFTER `uv sync` (otherwise uv sync removes it). Fixed systemd service `--foreground` → no flag (foreground is default).

## [0.1.0b109] - 2026-02-17

### Fixed

- **Linux install script** — PyGObject now installed via pip (compiled for Python 3.11) instead of relying on system packages. Added build deps (`libgirepository-2.0-dev`, `libcairo2-dev`). Script now refuses to run as root/sudo to prevent permission issues.

## [0.1.0b108] - 2026-02-17

### Added

- **Linux install script** — `scripts/linux-install.sh` installs all system dependencies (portaudio, espeak-ng, PyGObject, AppIndicator), creates venv, installs systemd service. Supports `--gpu` for CUDA acceleration. Works on Debian/Ubuntu, Fedora, and Arch.
- **Renamed macOS install script** — `scripts/macos-install.sh` (was `brew-rebuild.sh`) for consistency.

## [0.1.0b107] - 2026-02-17

### Fixed

- **State overwritten during shutdown** — `_persist_state()` was saving `active_agent: null` when agents unregistered during HTTP server teardown. Now skipped when `_running=False`. Engine `_running` is set to False before HTTP server stop to prevent stale writes.

## [0.1.0b106] - 2026-02-17

### Fixed

- **State restore timing** — `_restore_state()` now runs before HTTP server starts (was running 9s after agents registered). Preferred agent and output mode are correctly set when SSE agents connect.
- **Restore listening on restart** — `daemon.restore_listening` set to `true` in config. Engine now restores listening state across restarts.

## [0.1.0b105] - 2026-02-17

### Fixed

- **Tray app crash** — AppKit UI updates (icon, menu, tooltip) were called from SSE streaming thread. macOS requires all AppKit calls on the main thread. Now dispatches via `PyObjCTools.AppHelper.callAfter()`.

## [0.1.0b104] - 2026-02-17

### Added

- **Engine state persistence** — Saves active agent, output mode, and listening state to `~/.voxtype/state.json`. Restores output mode and preferred agent on restart. Config option `daemon.restore_listening` (default: false) controls whether listening state is restored.
- **Preferred agent reconnect** — When an agent reconnects after restart and matches the saved preferred agent, it becomes the current agent automatically.

### Fixed

- **Field label acronyms** — Settings UI now correctly shows "Preload TTS", "Preload STT", "VAD", "URL" etc. instead of "Preload Tts", "Preload Stt".

## [0.1.0b101] - 2026-02-17

### Fixed

- **Number inputs perfectly aligned** — Switched from `type="number"` to `type="text"` with `inputmode="numeric"`. Eliminates hidden spinner space that caused misalignment with other fields.

## [0.1.0b100] - 2026-02-17

### Changed

- **Section grouping from UI hints** — Tab groups are now defined in UI hints JSON (`groups` field on tabs), not hardcoded. The generator emits group definitions, SettingsSection reads them. Tabs without `groups` render flat.
- **Number spinners fully hidden** — Added `margin: 0` to webkit pseudo-elements to ensure arrows are completely invisible on all browsers including macOS Safari hover.

## [0.1.0b99] - 2026-02-17

### Fixed

- **Number inputs: hide native spinners** — Removed ugly browser up/down arrows from number fields. Numbers are now clean text-right inputs with number validation. No more misaligned spinners on hover.
- **Advanced tab: section grouping** — Multi-section tabs (Advanced has client, logging, stats, daemon, pipeline) now show section headers with dividers between groups for visual organization.

## [0.1.0b98] - 2026-02-17

### Fixed

- **Preset/Enum dropdowns show all options** — Default value is no longer hidden from the options list. "Default (value)" selects system default; all values including the default are individually selectable to force a specific choice.
- **Language presets show full names** — stt.language and tts.language dropdowns now show "English", "Italian", "Spanish" etc. instead of bare "en", "it", "es" codes. Uses labeled preset format `{value, label}`.
- **"Saved" auto-dismisses** — Save confirmation message disappears after 3 seconds instead of staying forever.

## [0.1.0b97] - 2026-02-17

### Changed

- **Settings UI uses generated config** — Tab definitions and field config (COMPLEX_KEYS, FIELD_PRESETS, SIZE_HINTS, ENUM_FIELDS) are now auto-generated from Pydantic model + UI schema hints via `_future/ui-schema/generate.py`. Removes hardcoded tab/field arrays from Svelte components.
- **`_future/` gitignored** — Generator tooling lives in a separate private repo, only generated output is committed.

## [0.1.0b96] - 2026-02-17

### Fixed

- **[object Object] for client config** — `client` section was missing from `list_config_keys()` sections list. Now properly expands to client.url, client.status_bar, client.clear_on_start individual fields.
- **Numbers right-aligned and compact** — NumberField now uses `text-right` and reduced widths (w-20/w-24/w-28).
- **Input widths reduced** — StringField (w-24/w-36/w-48), EnumField (w-48), all tighter and visually aligned.
- **Tooltip wrapping** — Changed from `max-w-xs` to `max-w-sm` with `break-words` for long descriptions.
- **Size hints expanded** — More fields (beam_size, channels, speed, timeout) now get compact "narrow" sizing.

### Added

- **Preset dropdowns for STT/TTS fields** — stt.model, stt.realtime_model, stt.language, tts.language now show dropdown with common presets + "Custom…" option for free-form entry. First option is always "Default (value)".
- **Literal types for STT compute_type/device** — Converted from plain `str` to `Literal["int8","float16","float32"]` and `Literal["auto","cpu","cuda","mlx"]`. JSON Schema now emits proper enum → automatic dropdown in UI.
- **pipeline.submit_filter and pipeline.agent_filter** added to COMPLEX_KEYS (edit via config.toml).

## [0.1.0b95] - 2026-02-17

### Added

- **Tray hover tooltip shows status** — Hovering the tray icon now shows "VoxType — Listening", "VoxType — Loading STT…", "VoxType — Idle", etc. Updates dynamically on every state change.

## [0.1.0b94] - 2026-02-17

### Improved

- **Settings UI polish** — Horizontal layout (label left, control right) for cleaner rows. Field details (description, key, env_var, default) moved into info tooltip. Dynamic input widths based on key name (port→narrow, host→medium). Enum fields show "Default (value)" option with capitalized labels. Save bar hidden when clean, added Cancel button with `resetDirty()`.

### Fixed

- **Tooltip.Provider missing** — Added `Tooltip.Provider` wrapper in layout to fix `Context "Tooltip.Provider" not found` crash.

## [0.1.0b93] - 2026-02-17

### Added

- **Tray `restarting` state** — New distinct state shown when engine restart is triggered from tray. Shows blue icon with "Restarting..." status text. SSE disconnect is suppressed during restart (stays blue instead of flashing red). Clears automatically when engine reports loading/idle/listening.

## [0.1.0b92] - 2026-02-17

### Fixed

- **Tray icon color code** — Four distinct colors for four states: red = disconnected (server unreachable), blue = loading/restarting (connected, preparing), yellow = idle (ready), green = listening. Loading previously reused the yellow idle icon; now uses the dedicated blue `voxtype_loading` icon.

## [0.1.0b91] - 2026-02-17

### Fixed

- **Tray icon shows red during loading** — Loading state previously showed yellow (idle) icon, now shows red (muted) icon like disconnected. Color semantics: red = not ready (disconnected/loading), yellow = idle (ready), green = listening.

## [0.1.0b90] - 2026-02-17

### Changed

- **Settings UI rebuilt with shadcn-svelte** — Replaced inline vanilla HTML/CSS/JS with a proper SvelteKit SPA using shadcn-svelte components (bits-ui headless primitives + Tailwind CSS). Dark theme matching Claude/ChatGPT aesthetic. Auto-generated form controls from Pydantic JSON Schema. Served at `/ui/` from existing FastAPI server, `/settings` redirects. Old inline HTML kept as fallback if build output missing.

## [0.1.0b89] - 2026-02-17

### Added

- **Settings UI** — Web-based configuration page served at `http://127.0.0.1:8770/settings`. Auto-generates form controls from Pydantic JSON Schema. Dark theme, tabbed layout (General, Audio, STT, TTS, Hotkey, Output, Server, Advanced). Tray "Settings" now opens the browser instead of a text editor.
- **Italian submit triggers in config defaults** — Italian was present in `input_filter.py` but missing from `config.py` defaults and template. Now all 5 languages (it, en, es, de, fr) are included in both places.

## [0.1.0b88] - 2026-02-17

### Fixed

- **Config file overwritten on `config set` and `config shortcuts`** — `_write_config()` rebuilt the entire file from scratch, destroying comments and formatting. `_save_shortcuts()` used `toml.dump()` which stripped all comments. Both now use `tomlkit` to preserve comments, formatting, and structure.
- **Replaced `toml` dependency with `tomlkit`** — `toml` (unmaintained) replaced by `tomlkit` which preserves comments and formatting on round-trip.

## [0.1.0b87] - 2026-02-17

### Improved

- **`models list` shows configured TTS engine** — System TTS engines (espeak, say) now shown below the models table with availability status.
- **`say.py` TTS logging** — macOS `say` backend now logs failures (not available, non-zero exit, subprocess error) instead of failing silently.

## [0.1.0b86] - 2026-02-17

### Fixed

- **espeak TTS fails silently in daemon mode** — `_detect_espeak()` stored only the command name ("espeak"), not the full path. In daemon environments where PATH may differ, the subprocess could fail to find the binary. Now stores the absolute path from `shutil.which()`. Also added logging for all espeak failure modes (binary not found, non-zero exit, subprocess error).
- **TTS chain has no diagnostic logging** — Added logging at every step: app command received, agent switch dispatched, `_set_current_agent()` called, `on_agent_change` callback, `speak_text()` dispatch, and `tts.speak()` result. Silent failures are now impossible.

## [0.1.0b85] - 2026-02-16

### Fixed

- **Tray app not reflecting engine mode changes** — SSE status stream was not reading `output.mode` from engine status. Double-tap mode switch worked in the engine but the tray menu stayed stale.
- **Daemon has no log output** — `setup_logging()` was never called in daemon mode. Python logger had no handler, all `logger.info/warning` calls went nowhere. Now logs to `~/.local/share/voxtype/logs/engine.jsonl`.
- **TTS failures logged at wrong level** — `speak_text()` failures logged at DEBUG (invisible). Now: WARNING for TTS engine missing or speak failure, INFO for successful TTS dispatch.

## [0.1.0b84] - 2026-02-16

### Changed

- **Mode switch announces "keyboard mode" / "agent mode"** — Double-tap now speaks the mode name via TTS instead of the internal agent ID.

## [0.1.0b83] - 2026-02-16

### Fixed

- **TTS announce missing on mode switch to keyboard** — `set_output_mode("keyboard")` set `_current_agent_id` directly, bypassing `_set_current_agent()` and its `on_agent_change` emit. Now announces "agent keyboard" via TTS when switching to keyboard mode.

## [0.1.0b82] - 2026-02-16

### Changed

- **Double-tap hotkey toggles output mode (agents ↔ keyboard)** — Previously double-tap switched to the next agent. Now it toggles between agents mode and keyboard mode, allowing quick fallback to local keystroke injection when the CPU is busy. Restores the last active SSE agent when switching back to agents mode.

## [0.1.0b81] - 2026-02-16

### Fixed

- **KeyboardAgent reads submit from wrong location** — `_process_message()` read `submit` from top-level message key, but the engine and pipeline filters set it in `x_input.submit`. Result: submit was always False in keyboard mode, so `newline_keys` (shift+enter) was sent instead of `submit_keys` (enter).
- **CI: remove orphan tests for deleted `on_transition` parameter** — Two stress tests still passed `on_transition=` to `StateManager()` after the parameter was removed in b78.

## [0.1.0b75] - 2026-02-15

### Changed

- **Renamed `core/messages.py` → `core/openvip_messages.py`** — Disambiguates OpenVIP wire format messages from FSM `StateMessage` in `core/fsm.py`.
- **Renamed `docs/design/event-architecture.md` → `docs/design/communication.md`** — Updated to reflect correct terminology (FSM messages, not events) and current file structure.

## [0.1.0b74] - 2026-02-15

### Changed

- **Consolidated FSM into `core/fsm.py`** — Merged `state.py` (AppState, StateManager, VALID_TRANSITIONS) and `state_messages.py` (all FSM messages) into a single `core/fsm.py`. One file defines the entire state machine: states, transitions, and inputs. Old files removed. Test file renamed to `test_fsm.py`.

## [0.1.0b73] - 2026-02-15

### Changed

- **Split events.py into state_messages.py + events.py** — FSM messages (inputs to StateController) now live in `core/state_messages.py` with proper naming: notifications use past tense (`SpeechStarted`, `SpeechEnded`, `TranscriptionCompleted`, `PlayStarted`, `PlayCompleted`), commands use imperative (`HotkeyPressed`, `SwitchAgent`, `SetListening`, `DiscardCurrent`). Base class renamed from `StateEvent` to `StateMessage`. Observer callbacks (`EngineEvents`, DTOs) remain in `core/events.py`. Removed dead `HotkeyDoubleTapEvent`.

## [0.1.0b72] - 2026-02-15

### Fixed

- **Hardcoded Italian language fallback** — When `stt.language = "auto"`, the detected language from Whisper is now propagated through the full chain (`STTResult` → `TranscriptionCompleteEvent` → `_inject_text()`). Previously, auto-detection discarded the language and fell back to hardcoded `"it"`, breaking submit triggers for non-Italian users (e.g., "ok send" never matched because the pipeline thought the message was Italian).

## [0.1.0b67] - 2026-02-15

### Fixed

- **VAD race condition: flush/reset without lock** — `flush_vad()` and `reset_vad()` now hold `_vad_lock`, preventing concurrent modification of VAD state by controller thread (TTS start/end) while audio thread is processing chunks. This race condition could corrupt VAD internal state, causing the engine to appear "listening" while silently dropping all speech detection.
- **VAD LSTM state not reset after device reconnect** — After audio device reconnection, the Silero VAD LSTM hidden state (`_h`, `_c`, `_context`) is now reset. Stale state from the old device's noise floor could prevent speech detection on the new device.

## [0.1.0b66] - 2026-02-15

### Added

- **`--openvip-timeout-factor`** — Scales all wait timeouts in the protocol compliance suite. Default 1.0 for fast implementations, use higher values (e.g. 5.0) for slow ones. Compliance tests verify correctness, not performance — a slow but compliant server should pass. Applied to `_wait_until()` polling and `SSEConnection.wait_connected()`. Timeout error messages report both base and scaled values.

## [0.1.0b65] - 2026-02-15

### Changed

- **Split compliance tests into protocol and internal** — `test_openvip_protocol.py` (64 tests) contains the portable protocol compliance suite: zero voxtype imports, all tests via real HTTP/SSE. Can be copied to any OpenVIP implementation's repo as an executable spec. `test_openvip_internal.py` (19 tests) contains voxtype-specific tests using mock engine and TestClient. Shared infrastructure (mock classes, `live_url` fixture) moved to `conftest.py`.

## [0.1.0b64] - 2026-02-15

### Changed

- **E2E compliance tests** — Rewrote 10 agent message tests from mock-based to true e2e: SSE agent connects via real HTTP, messages posted and verified through the SSE stream. Zero access to server internals. Added `SSEConnection` helper, `live_url`/`e2e_client`/`sse_connect` fixtures. Server uses `port` property and `wait_started()` for reliable startup. Module-scoped server keeps 79 tests under 12s.

## [0.1.0b63] - 2026-02-15

### Added

- **Dual-mode compliance test suite** — Tests run in-process with mocks (default) or against a live OpenVIP server via `--openvip-url`. Tests depending on mock internals are marked `@pytest.mark.internal` and auto-skipped in external mode. Added `tests/conftest.py` with shared pytest hooks.

## [0.1.0b62] - 2026-02-15

### Added

- **Proactive audio device change detection** — Prevents SIGABRT crash when audio devices disconnect (e.g., AirPods removed). On macOS, a CoreAudio property listener via ctypes detects default input device changes and immediately aborts the PortAudio stream before the IOThread assertion fires. On Linux, a polling fallback monitors the default device every 2 seconds. New `AudioCapture.emergency_abort()` method for lock-free, thread-safe stream termination from any thread.

## [0.1.0b61] - 2026-02-15

### Added

- **OpenVIP compliance test suite** — 79 tests covering all protocol endpoints, message schemas, error codes, and edge cases. Tests validate status, control, speech, agent messages, SSE registration, content types, and schema enforcement against the OpenVIP spec. Designed for portability — can be extracted to the OpenVIP protocol repo as a standalone compliance suite.

## [0.1.0b60] - 2026-02-15

### Changed

- **Move HTTP server from Engine to AppController** — Engine is now a pure domain object with no HTTP awareness. AppController owns the HTTP server lifecycle (create, start, stop). The HTTP adapter routes protocol commands (`stt.*`, `engine.shutdown`, `ping`) to `engine.handle_protocol_command()` and application commands (`output.*`) to `controller._handle_app_command()`. Engine methods renamed to public API: `get_status()`, `handle_speech()`, `handle_protocol_command()`. SSEAgent creation moved from Engine to HTTP server. Status change notifications use a registered callback instead of direct server reference. Zero external API changes.

## [0.1.0b59] - 2026-02-14

### Changed

- **Separate protocol from application commands** — `engine._handle_control()` now only handles protocol-level commands (`stt.start`, `stt.stop`, `stt.toggle`, `engine.shutdown`, `ping`) directly. Application-level commands (`output.set_agent`, `output.set_mode`) are delegated to `AppController` via a registered handler. This cleanly separates OpenVIP protocol concerns from application behavior. Zero external API changes — tray and CLI work identically.

## [0.1.0b58] - 2026-02-14

### Removed

- **Dead code cleanup (~1050 lines)** — removed legacy `VoxtypeApp` orchestrator (`core/app.py`), `LiveStatusPanel` (`ui/status.py`), and `commands/` package (`AppCommands`, `CommandSchema`, `CommandParam`). These were from a previous architecture superseded by `AppController` + `StatusPanel` (HTTP polling). Zero references in production code or tests.

## [0.1.0b57] - 2026-02-14

### Fixed

- **Loading state stuck after engine init** — `_loading_active = False` at end of `init_components()` didn't push SSE status update, so tray and mux stayed on "loading" until the next state change. Now `_notify_http_status()` is called when loading completes.
- **Loading color inconsistency** — tray showed blue (dedicated loading icon), mux showed yellow. Both now show yellow (same as "off"/idle) — engine not ready but not disconnected.

## [0.1.0b56] - 2026-02-14

### Fixed

- **TTS dependency check for system engines** — `voxtype dependencies check` now verifies that `espeak`/`say` binaries are actually installed in PATH, instead of silently skipping the check.
- **TTS default engine per platform** — default TTS engine is now `say` on macOS (built-in) and `espeak` on Linux.
- **Slow test moved to slow suite** — `test_sse_error_reports_reconnecting` (1s) marked as `@pytest.mark.slow`, excluded from default test run.

## [0.1.0b55] - 2026-02-14

### Changed

- **Unified display state resolution** — new `voxtype.status.resolve_display_state()` function replaces duplicated state logic in tray and mux. Both now show consistent state names ("loading", "listening", "idle", "standby") and styles. Unicode escape sequences replaced with literal characters (`●`, `○`, `·`).

## [0.1.0b54] - 2026-02-14

### Added

- **Tray and mux show loading state during engine startup** — tray shows loading icon while models are loading (`loading.active=true`). Agent mux status bar shows "loading" (warn). No state machine changes — reads existing `platform.loading.active` field from SSE status stream.

## [0.1.0b53] - 2026-02-14

### Fixed

- **Agent disconnect fallback to `__keyboard__`** — when the current SSE agent disconnected, `unregister_agent()` fell back to `_agent_order[0]` which was `__keyboard__` (registered first). This caused `current_agent` to become null (reserved agent hidden from visible). Now falls back to the first visible agent, or None if no visible agents remain. Agents reconnecting after restart now correctly become current.

## [0.1.0b52] - 2026-02-14

### Added

- **Comprehensive regression tests for keyboard/agent mode** — covers all scenarios: agent mode with no SSE agents, last agent disconnect, visible_agents exclusion, keyboard mode at startup, message routing after keyboard-first registration. 466 total tests.

## [0.1.0b51] - 2026-02-14

### Fixed

- **Agent mode: messages routed to keyboard instead of SSE agent** — regression from b48: `register_agent()` auto-set `__keyboard__` as current agent because it was registered first. Now reserved agents (`__keyboard__`) are never auto-selected as current; first real SSE agent becomes current instead.

## [0.1.0b50] - 2026-02-14

### Changed

- **Extract `_set_current_agent()` method** — consolidated the repeated set + emit + notify tripletta into a single method. All agent switch paths (hotkey, voice filter, API, mode switch, unregister fallback) now go through `_set_current_agent(agent_id, idx)`, eliminating the risk of forgetting to notify SSE subscribers.

## [0.1.0b49] - 2026-02-14

### Fixed

- **Agent switch not pushing SSE status update** — switching agents via voice filter, hotkey, or API changed `current_agent_id` internally but didn't notify SSE `/status/stream` subscribers, so mux status bars and tray app didn't update until the next state transition. Now `_notify_http_status()` is called on every agent switch.

## [0.1.0b48] - 2026-02-14

### Changed

- **KeyboardAgent always registered at startup** — KeyboardAgent is now created and registered regardless of initial output mode. Mode switch (`keyboard` ↔ `agents`) only changes `current_agent_id` without creating/destroying the agent. Saves and restores the last selected SSE agent when switching back from keyboard mode.

## [0.1.0b47] - 2026-02-14

### Fixed

- **Output mode switch not routing messages** — switching from Agents to Keyboard in the tray menu changed the mode flag but `current_agent` stayed on the SSE agent, so messages kept going to agents. Now `_set_output_mode("keyboard")` sets `__keyboard__` as current agent, and switching back restores the first SSE agent.

## [0.1.0b46] - 2026-02-14

### Changed

- **Tray app: polling → SSE streaming** — replaced 100ms GET /status polling with `subscribe_status()` SSE push. Status updates arrive instantly on state transitions. Automatic reconnection with backoff.
- **Agent mux: polling → SSE streaming** — replaced 0.5s polling for status bar with `subscribe_status()` SSE push. Removed `sse_connected` coordination event (no longer needed — engine pushes status on agent registration).

## [0.1.0b45] - 2026-02-14

### Added

- **SSE `/status/stream` endpoint** — push-based status updates via Server-Sent Events. Engine notifies all subscribers on state transitions and agent connect/disconnect. Keepalive comments every 30s.
- **`output.set_agent:NAME` control command** — colon-separated format for switching agents via `/control`, consistent with `output.set_mode:MODE`.

### Fixed

- **Tray agent switch not working** — clicking a different agent in the tray Target submenu had no effect because the `on_target_change` callback was never registered. Now sends `output.set_agent:NAME` to the engine.

### Changed

- **Voice agent switching enabled by default** — `pipeline.agent_filter.enabled` now defaults to `True`. Say "agent claude" or "agent cursor" to switch agents by voice.

## [0.1.0b44] - 2026-02-14

### Changed

- **Faster PTY status bar polling** — reduced agent status polling from 3.0s to 0.5s for near-instant idle/listening feedback. Periodic redraw (2s) unchanged — it only serves to survive child app full-screen redraws.

## [0.1.0b43] - 2026-02-14

### Fixed

- **PTY status bar not showing idle state** — engine state "off" was not matched by the `== "idle"` check, so the status bar showed "listening" (green) even when idle. Now checks for active states explicitly: "listening", "recording", "transcribing", "playing" → green; everything else → "idle" grey.
- **Revert tray menu bar text** — removed colored title text from macOS menu bar (tray shows icon only, as intended). Status display belongs in the PTY status bar.

## [0.1.0b42] - 2026-02-14

### Fixed

- **Audio engine crash (heap corruption)** — sounddevice output (`sd.play()`) was called from multiple daemon threads while the mic input stream callback ran on PortAudio's IOThread, causing concurrent access to PortAudio's non-thread-safe global session. All output playback is now serialized through a single worker thread via a queue. Fire-and-forget semantics preserved — one play does not block the next.

### Added

- **Status bar text in macOS menu bar** — shows agent name + state ("Idle" in grey, "Listening" in green) next to the tray icon. Uses NSAttributedString for colored text via pystray monkey-patch.
- **VoxType capitalization** — fixed "Voxtype" → "VoxType" in tray About menu.

## [0.1.0b41] - 2026-02-14

### Fixed

- **Crackling on transcribing/ready sounds** — these files were mono while the output device is stereo. Converted to stereo (dual-channel) to match up-beep/down-beep format. All bundled sounds are now uniformly 48kHz stereo WAV.

## [0.1.0b40] - 2026-02-14

### Changed

- **Resample bundled sounds to 48kHz WAV** — all beep/feedback sounds converted from 24kHz MP3 to 48kHz WAV (native output device sample rate). Eliminates PortAudio on-the-fly resampling that caused crackling artifacts. Files are pre-loaded into memory at ~158KB total.

## [0.1.0b39] - 2026-02-14

### Changed

- **Replace afplay/paplay with sounddevice for audio playback** — beep sounds now play in-process via `sounddevice` + `soundfile` instead of spawning external processes (`afplay` on macOS, `paplay`/`aplay` on Linux). Eliminates ~1 second of subprocess overhead per beep (measured: 1.38s → 0.47s for a 0.34s file). Bundled sounds are pre-loaded into memory at import time for zero-latency playback. Falls back to system commands if sounddevice is unavailable.

### Fixed

- **Tray icon delay when resuming from idle** — combined with the sounddevice change, the PLAYING→LISTENING transition is now ~1 second faster, making the tray icon update near-instant after the start beep.

## [0.1.0b38] - 2026-02-14

### Fixed

- **Tray icon delay when resuming from idle** — tray treated the PLAYING state (mic muted during start beep) as "off", so the icon stayed gray until the beep finished + one poll cycle. Now maps "playing" as an active state, matching the status bar behavior. Icon turns green immediately on idle→listening, same as listening→idle.

## [0.1.0b37] - 2026-02-14

### Fixed

- **Status bar shows idle when engine is off** — selected agent now shows "● agent · idle" in gray when engine is in idle state (hotkey toggle). Non-selected agents continue showing "○ agent · standby" in yellow. Previously, the selected agent kept showing "listening" even after the engine was paused.

## [0.1.0b36] - 2026-02-14

### Fixed

- **Agent launch hides command errors** — clear screen was happening after `session.start()`, wiping any immediate error output from the child process (e.g., "command not found"). Now clears before launching so errors are always visible.

## [0.1.0b35] - 2026-02-14

### Changed

- **Rename `derive_message()` → `fork_message()`** — clearer name for the message derivation function in pipeline. Pre-release API cleanup.
- **`PipelineAction(str, Enum)` → `PipelineAction(StrEnum)`** — use Python 3.11 native StrEnum.
- **Fix mypy errors in `PipelineLoader`** — `_build_step` now returns `Filter | Executor | None` instead of `object`.
- **Pin ruff `>=0.14.0,<0.15.0`** — prevents version drift between local and CI.
- **Xvfb for Linux CI** — `xvfb-run` provides virtual X11 display so tray/icon tests run on headless Linux.

## [0.1.0b34] - 2026-02-14

### Changed

- **Pre-release cleanup** — removed dead code (`VoxtypeError` class, unused), extracted shared `_normalize()`/`_tokenize()` from pipeline filters into `pipeline/filters/_text.py`, fixed `pyproject.toml` target-version mismatch (py310 → py311), removed redundant `typer` from dev extras. Added debug logging for partial transcription errors in engine.

### Removed

- Stale debug/build files scrubbed from git history via `git filter-repo`

## [0.1.0b33] - 2026-02-14

### Changed

- **Fast test suite: 452 tests in 1.2s** — marked 23 integration tests (app bundle, http server, race conditions, thread safety) as `@pytest.mark.slow`. Default `pytest` runs only fast logic tests. CI runs all with `pytest -m ''`.
- **Tray: readable Status and About text** — removed `enabled=False` from status line and version text. Items are now full-contrast black instead of greyed out.

## [0.1.0b32] - 2026-02-14

### Fixed

- **Test suite 11.6s → 6.3s** — controller `stop()` now sends a sentinel to wake the worker thread immediately instead of waiting up to 100ms for the `queue.get(timeout=0.1)` to expire. Each of ~30 engine/controller tests was wasting ~100ms on shutdown.

## [0.1.0b31] - 2026-02-14

### Fixed

- **Output mode switch crash** — switching from agents to keyboard via tray crashed with `AttributeError: '_config'`. Typo: `self._config` → `self.config`. Added 5 tests covering mode switching (keyboard→agents, agents→keyboard, noop, preservation of existing agents, invalid mode).

## [0.1.0b30] - 2026-02-14

### Added

- **Tray: Settings menu item** — opens `~/.config/voxtype/config.toml` in the default editor. Uses `open -t` on macOS, `xdg-open` or `$EDITOR` on Linux.
- **Tray: About submenu** — version info moved from main menu into an About submenu.

### Changed

- **Tray: version removed from main menu** — no longer shows raw version string at the bottom of the dropdown.

## [0.1.0b29] - 2026-02-14

### Changed

- **Submit triggers: multi-word only** — removed all single-word triggers (`submit`, `send`, `go`) from defaults. Single words trigger too easily during normal speech. Only multi-word sequences like `["ok", "send"]` remain.
- **Config template: DE/FR examples** — added commented German and French trigger examples alongside English.

## [0.1.0b28] - 2026-02-14

### Changed

- **Submit filter: English-only default** — removed hardcoded Italian/Spanish/German/French triggers from code defaults. Only English triggers ship by default. Users add their language via `[pipeline.submit_filter.triggers]` section in config.
- **Config template: expanded TOML triggers** — triggers shown as multi-line arrays under `[pipeline.submit_filter.triggers]` instead of unreadable single-line JSON.

## [0.1.0b27] - 2026-02-14

### Changed

- **Tray polling 500ms → 100ms** — faster visual feedback on hotkey toggle (icon color change is now near-instant).
- **Config template cleanup** — `create_default_config()` now generates all values commented out. Only non-default values need to be uncommented.

## [0.1.0b26] - 2026-02-14

### Fixed

- **Hotkey toggle bounces back** — tray and engine both registered a hotkey listener on the same key, causing two toggles per tap (OFF→LISTENING→OFF cancelled out as instant bounce). Removed the tray's listener — hotkey is the engine's responsibility.

## [0.1.0b25] - 2026-02-14

### Fixed

- **No audio feedback on brew install** — `.gitignore` pattern `sounds/` was excluding `src/voxtype/audio/sounds/*.mp3` from the sdist tarball. Changed to `/sounds/` to only ignore the root-level originals directory.

## [0.1.0b24] - 2026-02-14

### Fixed

- **Engine crash on brew install** — removed `rm_rf` of PyAV `.dylibs/` from brew formula. The hack prevented the install_name_tool warning but broke `av` at runtime (dlopen failure), causing the engine to crash in a respawn loop.

### Changed

- **`src/voxtype/libs/` — pure Python replacement library** — moved `metaphone()` and `levenshtein_distance()` into `voxtype.libs.jellyfish`, a drop-in module with the same interface as the external `jellyfish` package. To switch back: change `from voxtype.libs.jellyfish import ...` to `from jellyfish import ...`.
- **`uvicorn[standard]` → `uvicorn`** — removed `[standard]` extras which pulled in `watchfiles` (another Rust extension with the same install_name_tool issue). `watchfiles` is only used for `--reload` in development, not needed in production.

### Removed

- **jellyfish dependency** — replaced with pure Python in `voxtype.libs.jellyfish`. The jellyfish Rust extension (`_rustyfish.so`) caused Homebrew's `install_name_tool` to fail with "header too small" during `brew install`.

## [0.1.0b23] - 2026-02-13

### Removed

- **jellyfish dependency** — replaced with pure Python `_metaphone()` and `_levenshtein_distance()` in `agent_filter.py`. The jellyfish Rust extension (`_rustyfish.so`) caused Homebrew's `install_name_tool` to fail with "header too small" during `brew install`. Since these functions are only called on short agent names during occasional voice commands (not a hot path), the pure Python implementation has no meaningful performance impact.

## [0.1.0b20] - 2026-02-13

### Added

- **Microphone permission support** — Swift launcher now requests mic permission (shows "Voxtype" in dialog). `NSMicrophoneUsageDescription` added to Info.plist. Without this, macOS silently feeds zeros to the audio stream.
- **Microphone permission in `/status`** — new `platform.permissions.microphone` field. Tray shows "Grant Microphone Permission" menu item when not granted, clicking opens System Settings → Microphone directly.
- **`voxtype.platform.microphone` module** — `is_microphone_granted()` (cached 5s) and `open_microphone_settings()`.

### Fixed

- **Brew `post_uninstall` cleanup** — now removes Accessibility TCC entry via `tccutil reset`.

## [0.1.0b19] - 2026-02-13

### Added

- **macOS .app bundle via Homebrew** — `brew install` now creates `/Applications/Voxtype.app` so macOS shows "Voxtype" (not "Python") in mic indicator, Accessibility settings, and Activity Monitor.
- **Accessibility permission in `/status`** — new `platform.permissions.accessibility` field reports whether Accessibility is granted. Tray shows "Grant Accessibility Permission" menu item when missing, clicking opens System Settings directly.
- **Shared accessibility utility** — `voxtype.platform.accessibility` module with `is_accessibility_granted()`, `request_accessibility()`, `open_accessibility_settings()`. Cached (5s TTL) for polling efficiency.

### Fixed

- **Brew uninstall cleanup** — `post_uninstall` now stops brew service and kills engine/tray processes (not agent sessions).

## [0.1.0b18] - 2026-02-13

### Fixed

- **`__keyboard__` agent hidden from API and UI** — internal agents (like `__keyboard__`) are no longer visible in `/status`, tray, or status panel. `RESERVED_AGENT_IDS` set + `visible_agents`/`visible_current_agent` properties centralize filtering. HTTP SSE endpoint returns 403 for reserved agent IDs (security hardening).

## [0.1.0b17] - 2026-02-13

### Fixed

- **Tray output mode toggle works** — polling was overwriting the user's keyboard/agents selection every 500ms with the engine's reported mode. Now the tray owns the output mode (from config), polling no longer touches it.

## [0.1.0b16] - 2026-02-13

### Changed

- **Zero-config post-install** — both `brew install` and `curl | bash` produce a ready-to-use install. No extra commands needed: just `voxtype agent claude`. Models auto-download on first engine start, service is managed automatically.
- **`voxtype setup` skips service if Homebrew is active** — detects `brew services` and avoids creating a duplicate plist.
- **Simplified Homebrew caveats** — removed `voxtype setup` instruction; models download automatically.

## [0.1.0b15] - 2026-02-13

### Fixed

- **Daemon respects config output mode** — removed forced `agents` override in daemon mode. If config says `mode = "keyboard"`, the daemon creates a KeyboardAgent and injects keystrokes into the focused window (global dictation). Tray now shows the correct mode.

### Added

- **Tray: Advanced submenu** with "Restart Engine" — restarts the OS service (launchd/systemd) without leaving the tray. Useful after config changes.

## [0.1.0b14] - 2026-02-13

### Fixed

- **`brew-rebuild.sh` works on Linux** — uses `$(brew --prefix)` instead of hardcoded `/opt/homebrew`, handles BSD/GNU `sed` and `shasum`/`sha256sum` differences, derives all paths relative to project dir.

### Changed

- **openvip SDK path** — moved from `nottoplay/openvip-sdks` to `openvip-dev/sdks` across `pyproject.toml`, `uv.lock`, `brew-rebuild.sh`, and `publish.sh`.

### Added

- **`docs/notes/installation-guide.md`** — comprehensive install guide: macOS/Linux channel comparison, service management, cross-platform installer landscape research, reusable pattern for future projects.

## [0.1.0b13] - 2026-02-13

### Added

- **`install.sh`** — `curl | bash` installer (Ollama-style): detects OS, installs uv + voxtype, runs setup wizard. Supports `--skip-setup` and `--uninstall`.
- **`scripts/publish.sh`** — interactive PyPI publish workflow: tests, builds + uploads openvip then voxtype, creates GitHub release. Supports `--dry-run`.

## [0.1.0b12] - 2026-02-13

### Removed

- **Dead CLI commands** — removed `listen`, `execute`, `transcribe`, `devices`, `logs`, `completion`, `init`, `cmd`, `backends` (18 → 9 commands).
- **Engine start flags** — removed `--keyboard/-K`, `--agents/-A`, `--model/-m`, `--language/-l`. Mode comes from config; daemon always uses agents mode.
- **Models subcommands** — removed `use` (use `config set stt.model X`) and `resolve` (auto-pull at engine start).
- **Config subcommands** — removed `path` and `shortcuts`.
- **speak `--no-engine`** — engine is now auto-detected; falls back to in-process TTS automatically.

### Changed

- **`models download` → `pull`**, **`models clear` → `rm`** — aligned with Ollama/Docker conventions.
- **Default hotkey → Right Command** on macOS (`KEY_RIGHTMETA` instead of `KEY_LEFTMETA`).
- **Service plist/unit simplified** — `engine start -d` without `--agents` (daemon always implies agents mode).
- **Tray starts in "disconnected" state** — red icon until engine responds, instead of silent yellow.

### Added

- **`voxtype setup`** — first-time wizard: creates config, downloads models, installs service, prompts Accessibility permission.
- **Auto-pull models at engine start** — missing models are downloaded automatically instead of exiting with an error.

## [0.1.0b11] - 2026-02-13

### Changed

- **Tray icons: colored circle + white mic** — state conveyed by background color (green=listening, yellow=idle, blue=loading, red=disconnected) using approved SVG mic design. Monkey-patched pystray for crisp Retina rendering (NSImage at @2x pixels with point-size declaration).

## [0.1.0b10] - 2026-02-13

### Fixed

- **Tray icon adapts to dark/light menu bar** — pystray ignores `template=True`, so the NSImage was never marked as template. Monkey-patched `_assert_image` to call `setTemplate_(True)`. Icons regenerated at correct 18x18 @1x / 36x36 @2x size per Apple HIG.

## [0.1.0b8] - 2026-02-13

### Fixed

- **Agent starts without engine** — `voxtype agent` no longer blocks with an error if the engine is not running. It starts immediately showing "connecting..." in the status bar and reconnects automatically when the engine becomes available.

### Changed

- **Redesigned icons** — circular background (was rounded square), mic centered at 75% fill, gap below base filled. SVG versions added alongside PNGs.
- **Tray hides from Dock** — `_hide_dock_icon()` sets `NSApplicationActivationPolicyAccessory` so only the tray icon shows, no Dock tile.

### Added

- **`scripts/generate_icons.py`** — generates all icon assets (SVG + PNG tray icons, `.icns` app icon).
- **`scripts/brew-rebuild.sh`** — automates sdist build → formula SHA update → `brew reinstall`.
- **Homebrew `post_uninstall` cleanup** — `brew uninstall voxtype` now stops the tray, unloads the LaunchAgent, and removes the `.app` bundle automatically.
- **Homebrew caveats** — `brew info voxtype` shows service/tray start instructions.

## [0.1.0b7] - 2026-02-13

### Fixed

- **Mic indicator shows "Voxtype" instead of "Python"** — the .app bundle launcher script was using `exec` which replaced the bash process with python, causing macOS to attribute mic access to "Python". Now runs python as a child process so the .app bundle identity is preserved.

## [0.1.0b6] - 2026-02-13

### Fixed

- **Service stop now actually stops** — `voxtype service stop` was using `launchctl stop` which only killed the process, but `KeepAlive: true` in the plist caused launchd to restart it immediately. Now uses `launchctl load/unload` to properly register/unregister the agent. Stop means stop.
- **Service status shows loaded state** — `voxtype service status` now distinguishes between "running", "stopped (service not loaded)", and "not installed".
- **Service install no longer double-starts on macOS** — `install()` already calls `launchctl load` (which starts the process); the CLI no longer calls `start()` redundantly after install on macOS.
- **Linux: added `is_loaded()` to systemd backend** — uses `systemctl --user is-active` for consistent status reporting across platforms.

## [0.1.0b5] - 2026-02-13

### Fixed

- **Tray shows stale agent after disconnect** — when the last agent disconnects, the tray UI now correctly clears the target list instead of showing the last connected agent.

## [0.1.0b4] - 2026-02-12

### Added

- **Accessibility permission prompt** — tray app calls `AXIsProcessTrustedWithOptions` at startup to trigger the macOS Accessibility permission dialog automatically, so users don't have to manually find the Python binary in System Settings.

## [0.1.0b3] - 2026-02-12

### Added

- **macOS .app bundle** — `voxtype service install` creates `/Applications/Voxtype.app` so macOS shows "Voxtype" with icon in Accessibility / Input Monitoring settings.
- **Tray icons** — green mic (listening), blue (idle), orange (loading), red (muted) PNG icons for the system tray.
- **App icon** — `.icns` bundle icon with green microphone design.

## [0.1.0b2] - 2026-02-12

### Fixed

- Replace deprecated `typer-slim[standard]` dependency with `typer` (v0.23.0 removed the `standard` extra).
- Fix PyPI classifiers: "Beta" status, remove unsupported Python 3.10/3.12.

### Added

- **Homebrew tap** — `brew install dragfly/voxtype/voxtype`.

## [0.1.0b1] - 2026-02-12

First public beta release.

### Added

- **Voice engine** with Faster Whisper STT, Silero VAD, and configurable TTS (Piper, MLX Audio).
- **OpenVIP protocol** — HTTP API for voice interaction: `/status`, `/control`, `/speech`, SSE agent messaging.
- **Agent multiplexer** (`voxtype agent claude`) — PTY-based session with merged stdin + voice input via SSE.
- **Single-command launch** — agent templates in config: `[agents.claude] command = ["claude"]`.
- **System service** — `voxtype service install/start/stop/status` via launchd (macOS) / systemd (Linux).
- **Status panel** — Rich Live TUI showing model loading progress, STT state, agents, hotkey info.
- **Status bar** — persistent last-row indicator (listening/standby/reconnecting) in agent sessions.
- **Session logging** — JSONL session files in `~/.local/share/voxtype/sessions/` with keystroke tracking.
- **Pipeline architecture** — filters (AgentFilter, InputFilter) and executors (InputExecutor, AgentSwitchExecutor) with PipelineLoader DI.
- **Hotkey support** — tap to toggle listening, double-tap to switch agent (evdev on Linux, pynput on macOS).
- **Multi-agent switching** — voice-activated agent switching with phonetic matching (jellyfish).
- **Hardware auto-detection** — CUDA, MLX (Apple Silicon), CPU fallback with automatic compute type selection.
- **Audio feedback** — configurable sounds for start/stop/transcribing/ready/sent events.
- **Tray app** — system tray icon with status polling and quick controls.
- **OpenVIP SDK integration** — all client-side HTTP uses `openvip.Client` (subscribe, get_status, speak, control).
- **CLI**: `voxtype engine start/stop/status`, `voxtype agent`, `voxtype speak`, `voxtype listen`, `voxtype config`, `voxtype service`, `voxtype dependencies`.
