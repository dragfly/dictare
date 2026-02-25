# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0b311] - 2026-02-25

### Added
- **Parallel cached TTS playback** — cached audio plays on background threads
  in the worker, bypassing the serialized generation queue. Multiple cached
  phrases play simultaneously instead of waiting in line.
- **Play counter for mic-pausing** — atomic counter tracks active plays across
  concurrent requests. Mic pauses on first play (0→1), resumes only when all
  plays finish (N→0). Replaces per-request PlayStarted/PlayCompleted.
- **`TTSEngine.check_cache()`** — base method for cache-aware engines.
  KokoroTTS implements it using resolved lang/voice parameters.

## [0.1.0b310] - 2026-02-25

### Fixed
- **Kill orphaned TTS workers on startup** — engine now runs `pgrep` to find
  and terminate stale worker processes before spawning a new one.

## [0.1.0b309] - 2026-02-25

### Fixed
- **TTS worker 403 spam** — orphaned workers now exit after 3 consecutive
  HTTP 403 errors (token expired = engine was restarted, no point retrying).

## [0.1.0b308] - 2026-02-24

### Changed
- **TTS cache max raised to 1000** files (~50-250 MB).

## [0.1.0b307] - 2026-02-24

### Added
- **TTS audio caching** — deterministic WAV cache using
  `sha256(engine|text|language|voice)`. Cache hit = instant playback
  (no model inference). LRU eviction via mtime, max 500 files.
  Cache dir: `~/.local/share/dictare/tts-cache/`.

## [0.1.0b306] - 2026-02-24

### Added
- **`GET /speech/voices`** — API endpoint returning available voices for the
  active TTS engine. Returns `{"engine": "kokoro", "voices": [...]}`.
  `dictare speak --list-voices` now queries this endpoint when engine is running.
- **`TTSEngine.list_voices()`** — base method (returns `[]`), implemented by
  Kokoro (reads voices.bin) and macOS say (reads `say -v ?`).

## [0.1.0b305] - 2026-02-24

### Added
- **`dictare speak --list-voices`** — lists all available voices for the
  current TTS engine with language, gender, and name. Works with Kokoro
  (53 voices across 9 languages).

## [0.1.0b304] - 2026-02-24

### Fixed
- **Language override not reaching Kokoro** — worker read `language` from
  `additional_properties` but `SpeechRequest` has it as a native field.
  Now reads `msg.language` directly.

## [0.1.0b303] - 2026-02-24

### Added
- **Per-request `voice` and `language` overrides** in `/speech` endpoint.
  Kokoro uses them to switch voice/language on the fly without restart.
  Other engines log and ignore unsupported overrides gracefully.

## [0.1.0b302] - 2026-02-24

### Fixed
- **Kokoro TTS wrong voice** — voice was hardcoded to `af_heart` (English)
  regardless of language setting. Now `_resolve_voice()` picks the correct
  per-language default (e.g., `ef_dora` for Spanish, `if_sara` for Italian).

## [0.1.0b301] - 2026-02-24

### Fixed
- **Kokoro TTS API update** — `Kokoro.from_pretrained()` was removed in
  kokoro-onnx 0.5.0. Now downloads model files from GitHub releases
  (~310MB model + 27MB voices) to `~/.local/share/dictare/models/kokoro/`
  and passes paths to `Kokoro(model_path, voices_path)`.
- **`dictare logs --tts`** — new flag to view TTS worker log (plain text).

## [0.1.0b300] - 2026-02-24

### Fixed
- **Kokoro TTS not spawning as worker** — `_worker_engines` was hardcoded
  to `{outetts, piper, coqui}`, missing kokoro. Now derived dynamically
  from `VENV_ENGINES.keys()` so any venv-based engine automatically gets
  a worker subprocess.

## [0.1.0b299] - 2026-02-24

### Removed
- **Coqui XTTS v2 hidden from UI** — removed from models.json. The
  coqui-tts package is abandoned and incompatible with torch>=2.6 and
  transformers>=4.46. Code kept in coqui.py for potential future use.

## [0.1.0b298] - 2026-02-24

### Fixed
- **Hotkey Capture button** — evdev capture now falls back to browser-side
  key detection when engine has no listener (macOS daemon mode). Browser
  keydown runs in parallel with engine capture — whichever fires first wins.
  Captures any key including pure modifiers (Right Command, Left Shift, etc.).

## [0.1.0b297] - 2026-02-24

### Fixed
- **Coqui TTS** — pass `COQUI_TOS_AGREED=1` env var to subprocess, fixing
  EOFError on license prompt. Remove wrong `repo`/`check_file` from
  models.json (Coqui uses its own model manager, not HuggingFace).

### Changed
- **Restart UX** — replaced top restart banner with footer status bar.
  After saving settings, an amber "Settings changed. Restart engine?" bar
  appears at the bottom (consistent with the engine status bar). Model
  selection no longer auto-restarts — user decides when to restart.
- **Dashboard mode toggle** — added Keyboard/Agents toggle buttons in the
  Engine card. Switches output mode immediately via control command (no
  restart needed). SSE pushes update, toggle reflects current state.

## [0.1.0b296] - 2026-02-24

### Fixed
- **Accordion spacing** — added margin between TOML accordion sections
  (e.g. Submit Filter / Agent Filter on Pipeline page).

## [0.1.0b295] - 2026-02-24

### Fixed
- **Parakeet download check** — `check_file` in models.json pointed to
  `model_fp16.onnx` which doesn't exist in the repo; changed to
  `encoder-model.int8.onnx`. Parakeet was already cached but the UI
  kept showing the download button.
- **`dictare speak` no in-process fallback** — removed the in-process TTS
  fallback that crashed trying to find `tts` binary in PATH. Now uses the
  running engine exclusively. Clean error messages: "Engine not running"
  when engine is down, "TTS failed: <detail>" on engine errors, with full
  stacktraces logged to the log file.

### Changed
- **Model/engine selectors removed from Settings** — `stt.model` and
  `tts.engine` dropdowns removed from Speech and Voice tabs. These are
  now selected exclusively via the Models page radio buttons.

## [0.1.0b294] - 2026-02-24

### Fixed
- **Uninstall requires confirmation** — trash button now shows a confirm dialog
  before removing the isolated environment.
- **Cannot uninstall active capability** — trash button hidden on the currently
  configured STT/TTS capability. Switch to another first, then uninstall.

## [0.1.0b293] - 2026-02-24

### Added
- **Engine status bar** — fixed bottom bar across all Settings pages. Shows
  orange "Engine restarting..." when engine goes down, green "Engine ready"
  when it comes back (auto-hides after 1.5s). Polls `/health` every 2s.

## [0.1.0b292] - 2026-02-24

### Fixed
- **TTS failure now reports error** — `handle_speech()` was ignoring the return
  value of `tts.speak()`, always returning `{"status": "ok"}`. Now returns
  `{"status": "error"}` when `speak()` returns `False`, so the CLI shows the
  error instead of silently claiming "Spoken".

## [0.1.0b291] - 2026-02-24

### Fixed
- **Parakeet download via capabilities** — `_run_capability_install` and
  `_run_model_download` now always use `snapshot_download(repo)` for model
  downloads. Previously, onnx-asr models tried `load_model()` which initializes
  the ONNX runtime (crashing with "model_path must not be empty").

## [0.1.0b290] - 2026-02-24

### Changed
- **Aligned card heights** — Models page uses a single CSS grid so STT and TTS
  cards in the same row share the same height. No more jagged columns.
- **Download button icon-only** — Download button now matches trash button style:
  ghost icon-only with tooltip on hover, saves card space.
- **Extracted capCard snippet** — card rendering uses a Svelte snippet for
  cleaner code reuse.

## [0.1.0b289] - 2026-02-24

### Added
- **Model selection via radio buttons** — Models page now has radio buttons on
  each capability card. Click a ready capability to select it, then Save to
  switch STT model or TTS engine with automatic engine restart.
- **`POST /capabilities/{id}/select`** — backend endpoint that maps capability
  ID to config key (stt.model / tts.engine), saves config, and restarts engine.
- **Green border on active model** — selected capability card has a green border
  for instant visual feedback.
- **Error hover tooltip** — download failures show "Download failed" with error
  details on hover. Errors are logged server-side.

### Changed
- **Radio enabled only when ready** — can only select capabilities that are fully
  installed (venv + model). Download first, then select.
- **Save bar for model changes** — bottom bar shows with Save/Cancel when
  changing the selected capability. Save triggers restart.

## [0.1.0b288] - 2026-02-24

### Added
- **Unified capabilities API** — `GET /capabilities` merges models.json with
  runtime checks (venv installed, model cached, platform, configured). Replaces
  separate model + engine status queries with one unified view.
- **Capability install/uninstall** — `POST /capabilities/{id}/install` orchestrates
  venv creation + model download in one step. `DELETE` removes the venv.
- **TTS capabilities in models.json** — say, espeak, piper, coqui-xtts-v2,
  outetts, kokoro registered alongside STT models. New fields: `venv`, `platform`,
  `builtin`.
- **Download/install logging** — model downloads and venv installs log start,
  completion, and errors.

### Changed
- **Models page redesign** — two-column layout (STT | TTS) showing all
  capabilities with download/uninstall buttons and progress bars.
- **Dashboard simplified** — removed TTS/STT engine sections (moved to Models).
  Dashboard now shows Engine status, Agents, and Permissions only.
- **General settings moved to Advanced** — editor and verbose now under
  Advanced > General sub-tab.
- **Models tab moved up** — now second in nav (after Dashboard).
- **Restart Engine button** — only shown on Advanced > Daemon sub-tab.

### Removed
- Old vyvotts-4bit, vyvotts-8bit, and legacy outetts model entries.

## [0.1.0b287] - 2026-02-24

### Fixed
- **Coqui TTS uses XTTS v2 model** — without explicit `--model_name`, coqui CLI
  defaulted to Tacotron2-DDC (English-only), silently ignoring `--language_idx`.
  Now always specifies `tts_models/multilingual/multi-dataset/xtts_v2`.
- **Coqui TTS logs errors** — `speak()` now logs stderr on subprocess failure
  instead of swallowing it silently.
- **Venv tests use tmp_path** — tests for missing venvs no longer fail when real
  venvs exist on the developer's machine.

## [0.1.0b286] - 2026-02-24

### Added
- **Kokoro TTS engine** — 82M-parameter neural TTS via `kokoro-onnx` (ONNX runtime,
  no PyTorch). #1 on HuggingFace TTS Arena, 9 languages, ~300MB model, 5x real-time
  on CPU. Set `tts.engine = "kokoro"` in config. Installable via Dashboard.

### Fixed
- **TTS venv install** — removed `openvip` from `_SHARED_DEPS` (not on PyPI).
  PYTHONPATH injection already makes it available. Unblocks all venv installs.

## [0.1.0b285] - 2026-02-24

### Fixed
- **`uv` discovery in launchd context** — `_find_uv()` now checks Homebrew paths
  (`/opt/homebrew/bin/uv`, `/usr/local/bin/uv`) when `shutil.which("uv")` fails
  due to launchd's minimal PATH. TTS venv installs now work from Dashboard.
- **Dashboard shows install errors** — failed TTS installs now display the error
  message inline below the engine name instead of silently appearing to succeed.

## [0.1.0b284] - 2026-02-24

### Added
- **TTS isolated venvs** — heavy TTS engines (piper, coqui, outetts) now install
  into isolated venvs at `~/.local/share/dictare/tts-env/{engine}/`, eliminating
  dependency conflicts between TTS and STT engines (e.g., numba vs numpy).
- **Dashboard Install/Uninstall buttons** — one-click install for TTS engines
  directly from the Settings UI. Progress streams via existing SSE.
- **API endpoints** — `POST /tts-engines/{engine}/install` and
  `DELETE /tts-engines/{engine}/install` for programmatic venv management.
- **Venv-aware engine detection** — piper and coqui `_detect_*()` methods now
  check venv bin directories as fallback. `check_all_tts_engines()` reports
  `needs_venv` and `venv_installed` status fields.

### Changed
- **piper-tts and pathvalidate removed from core dependencies** — now managed
  via isolated venv, reducing base install size and eliminating conflicts.
- **`/speech` endpoint returns proper HTTP errors** — engine mismatch → 409,
  TTS unavailable or empty text → 422 (no more `{"status":"error"}` with 200).
- **No in-process TTS fallback** — if the TTS worker fails to start, the engine
  reports TTS as unavailable (red in Dashboard) instead of silently dropping
  speak requests.
- **`handle_speech()` simplified** — always uses the running TTS worker proxy.
  Engine override rejected with clear error message pointing to Settings.

## [0.1.0b282] - 2026-02-24

### Changed
- **Rename VoxType → Dictare** across entire codebase — tray tooltips, About
  menu, FastAPI title, page titles, docstrings, and all tests updated.

## [0.1.0b281] - 2026-02-24

### Added
- **`dictare status` CLI command** — top-level command showing engine health,
  all TTS/STT engine availability with install hints, agent connections,
  and system permissions. Supports `--json` for scripting.
- **Dashboard tab in Settings UI** — first tab showing real-time engine status,
  TTS/STT engine availability with copy-to-clipboard install commands,
  agent list, and permission status. Updates via SSE.
- **All-engine health checks** — `check_all_tts_engines()` and
  `check_all_stt_engines()` in `utils/platform.py` probe all 5 TTS and 3 STT
  engines with lightweight availability checks.
- **Enhanced `/status` endpoint** — `engines` field in platform section reports
  availability of all TTS and STT backends (cached at startup).
- **Homebrew install mode detection** — install hints now show exact
  copy-pasteable commands with the correct Python path for Homebrew installs.

### Fixed
- **espeak install hint** — `brew install espeak` → `brew install espeak-ng`
  (espeak is deprecated upstream).
- **espeak detection in launchd** — fallback to `/opt/homebrew/bin/espeak-ng`
  when Homebrew PATH is not inherited by the service process.

## [0.1.0b279] - 2026-02-24

### Fixed
- **TTS worker crash detection** — engine now polls worker process every 0.5s
  instead of blocking 120s. If worker crashes immediately (e.g. missing
  dependency), engine detects it in <1s and falls back gracefully.

## [0.1.0b278] - 2026-02-24

### Changed
- **Unified native audio playback** — all TTS engines (piper, coqui, outetts)
  now use `play_wav_native()`: afplay on macOS, paplay/aplay on Linux.
  Eliminates sounddevice/PortAudio crackling from sample rate mismatch.
  See `docs/notes/audio-playback-architecture.md`.

## [0.1.0b277] - 2026-02-24

### Fixed
- **Piper crackling on macOS** — switched from sounddevice (PortAudio) to afplay
  (native CoreAudio) for WAV playback on macOS. PortAudio handles 22050 Hz
  poorly on macOS, causing crackling. afplay does native resampling correctly.

## [0.1.0b276] - 2026-02-24

### Fixed
- **`dictare speak` via HTTP** — CLI was sending `voice: null` causing server
  500 error, silently falling back to in-process TTS. Now omits null fields.
- **`/speech` endpoint null handling** — `handle_speech()` now treats null body
  values as "use default" instead of passing them to Pydantic validation.

## [0.1.0b275] - 2026-02-24

### Fixed
- **TTS proxy missing protocol fields** — SSE messages to worker were missing
  `id` and `timestamp`, causing Pydantic validation failure in the SDK's
  `parse_message()`. Worker silently dropped all speech messages.
- **TTS worker logs** — worker now logs to `~/.local/share/dictare/logs/tts-worker.log`
  in addition to stderr.

## [0.1.0b274] - 2026-02-24

### Added
- **Persistent TTS worker subprocess** — heavy TTS engines (outetts, piper, coqui)
  now run in a long-lived worker process that loads the model once. Eliminates
  8-9s startup penalty on every `speak()` call.
- **WorkerTTSEngine proxy** (`tts/proxy.py`) — implements `TTSEngine` interface,
  routes `speak()` to worker via SSE queue, blocks until completion.
- **TTS worker** (`tts/worker.py`) — connects as `__tts__` agent via openvip SDK,
  processes speech messages with persistent model.
- **Scoped Bearer token bypass** — `__tts__` (and other reserved agent IDs) can
  register via SSE with a scoped `register_tts` token generated per engine instance.
- **`POST /internal/tts/complete`** — endpoint for worker to signal speak completion.
- **OpenVIP protocol fixes** — `Message` base schema in OpenAPI spec, `SpeechRequest`
  now includes `id` + `timestamp` (was missing), `agent_id` optional field added.
- **OpenVIP SDK fixes** — `Message` base class, `parse_message()` factory,
  `Client(headers=...)` for Bearer auth, `subscribe()` yields `Message` (not just
  `Transcription`), `create_speech_request()` auto-generates `id` + `timestamp`.

## [0.1.0b273] - 2026-02-24

### Fixed
- **Loading state stays active until `start_runtime`** — UI no longer flashes
  "idle" between model loading and LISTENING transition.
- **Renamed `_loading_active` → `_loading`** for clarity.
- **Removed old fallback Settings UI** (`settings_ui.py`, 422 lines) — shadcn-svelte
  SPA is the only Settings UI now.
- **Fixed `.gitignore`** — `dist/` → `/dist/` (root-only) so `src/dictare/ui/dist/`
  is tracked; updated override from `voxtype` → `dictare`.

## [0.1.0b272] - 2026-02-24

### Changed
- **Audio reconnect circuit breaker**: max 5 reconnects in 60s window prevents
  reconnect storms from flaky USB hubs or rapid device changes.
- **Consecutive error threshold**: 3 consecutive PortAudio errors required before
  triggering reconnect (ignores transient single-frame glitches).
- **Unified `reconnect_reason` property** replaces `needs_reconnect()` + `is_stale()`
  on both `AudioCapture` and `AudioManager`. Returns `None` (healthy),
  `"callback_error"`, `"stream_inactive"`, or `"stream_stale"`.
- **Post-reconnect cooldown** (3s) lets the new stream stabilize before resuming.
- **`wait_for_audio()` verification** after each reconnect attempt catches zombie
  streams immediately instead of waiting for the 3s stale timeout.
- **Skip Pa_Terminate on first reconnect attempt** to avoid CoreAudio deadlocks.
- **Simplified engine main loop**: collapsed two-path reconnect (fast + slow stale
  check) into a single `reconnect_reason` check every 100ms.

## [0.1.0b269] - 2026-02-24

### Fixed
- **"Engine ready" log now shows actual state** (LISTENING or IDLE) instead of
  always "IDLE — waiting for trigger". Added `start_runtime: transitioned → LISTENING`
  log when session restore activates listening.

## [0.1.0b268] - 2026-02-24

### Changed
- **`agent_mode` is now a derived read-only property**, not a flag.
  `agent_mode = (_current_agent_id != KEYBOARD_AGENT_ID)`. Cannot go out of sync.
- **`output_mode` removed from session-state.json.** Mode is always derived from
  the active agent. Session file only stores: `active_agent`, `listening`, `last_active`.
- **Removed `_restore_listening` flag**, `_persist_state()` wrapper, `_agent_mode`
  backing field, debug traceback property, and `agent_mode` parameter from
  `create_engine()`. Total: -5 variables, -3 methods, -50 lines of mode comparison logic.
- **`KEYBOARD_AGENT_ID` constant** replaces all `"__keyboard__"` string literals.
- **`_restore_state()` now takes and returns `start_listening`** — no intermediate flags.

## [0.1.0b266] - 2026-02-24

### Fixed
- **`_save_state()` derives mode from current agent, not from `agent_mode` flag.**
  The flag could become stale after restoring a corrupted session. Now if
  `_current_agent_id='voice'` (a real SSE agent), mode is saved as `agents`
  regardless of the flag. Logs a warning when flag and agent disagree.
  Breaks the self-reinforcing loop where one bad save corrupted all future sessions.

## [0.1.0b265] - 2026-02-24

### Fixed
- **Removed vestigial `load_state()` call in `serve.py`** that bypassed
  `_restore_state()` and could crash on `None.get()` (session expired/missing).
  Listening restore is now exclusively handled by `engine._restore_state()`.

### Added
- **Version logged at startup and shutdown.** Startup: `dictare 0.1.0bXXX starting`,
  Shutdown: `Shutting down dictare 0.1.0bXXX (signal 15)`. Makes it trivial to
  verify which version saved the session state.

## [0.1.0b264] - 2026-02-24

### Added
- **`agent_mode` property with change tracking.** Every `agent_mode` change is
  logged with caller stack trace. This will catch whatever is flipping the engine
  to keyboard mode unexpectedly during session lifetime.
- **Enhanced shutdown save log** shows `_agent_mode` raw value, registered agents
  list, and `_running` flag for easier debugging.

## [0.1.0b263] - 2026-02-24

### Fixed
- **SIGTERM now saves session state before shutdown.** Previously, `request_shutdown()`
  (SIGTERM from launchd/systemd) set `_running=False` without saving, so the last
  state was lost. Now `save_session_before_shutdown()` is called explicitly.
- **Listening state restored from session.** The `listening` field was saved to
  `session-state.json` but never read back. Now the engine restarts in listening
  mode if the session was listening.
- **Comprehensive session lifecycle logging.** Cold start vs session restore,
  output_mode changes, listening restore, preferred agent wait, and
  save-before-shutdown are all logged with clear context.

## [0.1.0b262] - 2026-02-24

### Changed
- **Session-based state restore.** `state.json` → `session-state.json` with a
  `last_active` timestamp. If the last session is < 60 min old (quick restart,
  reboot), output_mode and preferred agent are restored. Otherwise, config.toml
  defaults apply (cold start after long pause or reinstall).
- **Preferred agent grace period (20s).** After restart, the engine waits 20s
  for the preferred agent to reconnect before falling back to the first
  available agent.

### Added
- **`dictare service install` auto-creates default config.** If `config.toml`
  doesn't exist, creates one from the template with commented defaults.

## [0.1.0b261] - 2026-02-24

### Added
- **`dictare version --deps`** — shows key dependency versions (openvip, faster-whisper, piper-tts, onnx-asr).

## [0.1.0b260] - 2026-02-24

### Changed
- **Rebuild from b238 base.** Clean rebuild discarding the broken authorization
  cascade (b239–b259). Only proven fixes cherry-picked onto the stable base.

### Fixed
- **VAD atomic close eliminates reconnect storm.** `close()` now does
  `self._model = None` atomically + `gc.collect()` instead of the two-step
  `del self._model.session` / `self._model = None` that left a race window.
- **Play ID counter on FSM worker thread.** Replaced racy `get_next_play_id()`
  (called from multiple engine threads) with an atomic counter incremented on
  the single FSM worker thread. Multiple concurrent TTS plays are tracked
  correctly.
- **Engine resilience: no exit on reconnect failure.** Engine now retries with
  30s backoff instead of breaking out of the run loop entirely.
- **STT exception logging.** Added `logger.exception()` on transcription
  failures instead of silently swallowing errors.
- **Piper TTS uses sounddevice via audio worker queue.** Replaces
  platform-specific subprocess calls (aplay/afplay) with `play_wav_sync()`
  routed through the serialized audio worker — consistent, cross-platform.

### Added
- **Background model download.** `ensure_required_models()` runs in a
  background thread so the engine starts immediately.
- **`/health` endpoint.** Liveness probe for service monitors.
- **`play_wav_sync()` utility.** Synchronous wrapper over the async audio
  queue for callers that need to wait for playback completion (TTS).
- `piper-tts` and `pathvalidate` as explicit dependencies.

## [0.1.0b238] - 2026-02-23

### Changed
- **Agent config: `live_dangerously_args` replaces `-danger` presets.** Each agent
  type now declares its own dangerous-mode args (e.g. `["--dangerously-skip-permissions"]`
  for Claude, `["--dangerously-bypass-approvals-and-sandbox"]` for Codex). Use
  `dictare agent <name> --live-dangerously` to activate. Eliminates 3 duplicate
  presets (sonnet-danger, opus-danger, chatgpt-danger) and gives the engine a
  semantic signal that the agent is running in dangerous mode.

## [0.1.0b235] - 2026-02-22

### Fixed
- **CI: fix `os._exit(1)` killing test process after 6 seconds.** The
  `engine.shutdown` handler spawned a watchdog thread that called `os._exit(1)`
  after 6s — this killed the entire pytest process at ~78% when running all
  784 tests (including slow). Watchdog now honours a cancellable event so
  tests can neutralize it.

## [0.1.0b234] - 2026-02-22

### Fixed
- **CI green: fix all ruff linting errors.** Unused imports, unsorted import
  blocks, unused variables in test_loop_audio, test_toml_sections,
  test_agent_template, and scripts/test-mic.
- **Remove CLI help text from config template.** Agent type usage examples
  (`dictare agent <name>`, `--continue`, etc.) belong in `--help`, not config.

## [0.1.0b233] - 2026-02-22

### Fixed
- **Settings UI: section extraction no longer bleeds across sections.** Comments
  after a non-owned `[section]` header (e.g. `# enabled = true` under `[pipeline]`)
  were incorrectly attributed to the next owned section (e.g. Agent Filter accordion
  showed Submit Filter content). Now comments stay with their parent section.

## [0.1.0b232] - 2026-02-22

### Changed
- **Submit filter triggers no longer hardcoded.** Default triggers are now empty —
  must be configured in `config.toml` under `[pipeline.submit_filter.triggers]`.
  Prevents unintended submit on phrases like "ok invia" when user hasn't
  explicitly opted in. Template examples retained as commented-out reference.

## [0.1.0b231] - 2026-02-22

### Changed
- **Transcribing sound disabled by default.** The typewriter loop during
  transcription is no longer needed with continuous VAD pipeline (speech is
  never lost). Opt-in via `audio.sounds.transcribing.enabled = true`.

## [0.1.0b230] - 2026-02-22

### Changed
- **Continuous VAD pipeline.** VAD now keeps running during TRANSCRIBING and
  INJECTING states instead of silently dropping audio chunks. Speech arriving
  during transcription is segmented by VAD and queued for sequential STT
  processing. No concurrent STT — same single-threaded model, just no more
  lost audio. PLAYING and OFF still mute the mic as before.

## [0.1.0b229] - 2026-02-22

### Fixed
- **Linux: tray icon deduplication removed.** The icon dedup added in b212
  was preventing AppIndicator from receiving icon updates. Restored b168
  behavior: every state change sets the icon unconditionally. Added logging
  to confirm the AppIndicator patch is applied.

## [0.1.0b228] - 2026-02-22

### Fixed
- **Linux: tray icons — revert to b168 temp file approach.** AppIndicator
  caches icons by path, so reusing bundled file paths caused stale/black icons.
  New temp file per update (with `.png` extension) forces AppIndicator to reload.

## [0.1.0b227] - 2026-02-22

### Fixed
- **Linux: tray icons point directly to bundled PNGs.** No more temp files —
  AppIndicator now reads icons straight from the installed package directory.
  Simpler, faster, nothing to break.

## [0.1.0b226] - 2026-02-22

### Fixed
- **Linux: tray icon colors lost.** Reverted AppIndicator icon caching (b213)
  back to the simple b168 approach — one temp file per update with `.png`
  extension. The content-hash caching was causing AppIndicator to show
  fallback icons instead of the colored mic circles.

## [0.1.0b225] - 2026-02-22

### Fixed
- **Linux: engine stuck in PLAYING state.** `sd.wait()` hangs indefinitely on
  ALSA/PulseAudio backends, preventing `PlayCompleted` from firing and leaving
  the FSM stuck. Replaced with polling loop + 10s timeout.
- **Linux: evdev listener silent death.** Replaced `sys.stderr.write` and silent
  `pass` on OSError with structured logging (`logger.warning`/`logger.error`).
  Device errors, thread exits, and startup info now appear in engine logs.

## [0.1.0b224] - 2026-02-22

### Fixed
- **PortAudio reinit deadlock.** `Pa_Terminate()` hangs when CoreAudio is in
  corrupted state (error -50 after device change). Reconnect now uses
  `emergency_abort()` (fast, lock-free) instead of `stop_streaming()`, and runs
  `sd._terminate()/sd._initialize()` in a thread with 3s timeout — skips if
  hung and tries to open a new stream anyway.

## [0.1.0b223] - 2026-02-22

### Fixed
- **Zombie audio stream detection.** After device changes, PortAudio could report
  stream as active while CoreAudio was corrupted (error -50). New health check
  tracks `_last_callback_time` in streaming callbacks, detects stale streams
  (no data for 3s), and forces reconnect. Post-reconnect verification waits for
  actual audio data before declaring success.

## [0.1.0b222] - 2026-02-22

### Added
- **Audio device selection.** Input and output device dropdowns in Settings > Audio
  as the first two fields. "Default (device name)" shows system default. New
  `audio.input_device` and `audio.output_device` config fields (2-level keys).
  Migration validator auto-migrates legacy `audio.advanced.device` to `input_device`.
  Reconnection respects configured device (falls back to system default after 5
  retries). `GET /audio/devices` API endpoint lists available devices. Status
  endpoint reports current audio devices. Output device routed to beep playback.

## [0.1.0b220] - 2026-02-22

### Fixed
- **Engine restarts to keyboard mode instead of agents.** On SIGTERM shutdown
  (tray restart), `_persist_state()` was never called before `_running` was set
  to False. Agents disconnecting during HTTP server teardown would then be the
  last "state" — but `_persist_state()` skipped because `_running=False`, leaving
  stale defaults in `state.json`. Now `_persist_state()` is called explicitly
  before disabling further saves.

## [0.1.0b219] - 2026-02-22

### Changed
- **Settings UI: normal fields above, TOML editors below.** In all tabs,
  user-configurable fields (toggles, inputs, dropdowns) now render above
  TOML/shortcuts editors for better discoverability.
- **Settings UI: spacing after TOML/shortcuts editors.** Added bottom margin
  after Save/Reset buttons to separate sections visually.

## [0.1.0b218] - 2026-02-22

### Fixed
- **Web UI engine restart now works.** `engine.restart` was missing from the
  `PROTOCOL_COMMANDS` routing set in `http_server.py`, so the command was routed
  to the app controller (which just logged it) instead of the engine (which
  actually restarts). One-character fix: added `"engine.restart"` to the set.

## [0.1.0b217] - 2026-02-22

### Added
- **STT and injection timing metrics.** Transcription logs now include `stt_ms`
  (STT processing time) and injection logs include `inject_ms` (time to deliver
  text to the agent). Enables diagnosing delays in the transcription pipeline.

## [0.1.0b216] - 2026-02-22

### Fixed
- **Restart Engine polling logic.** The web UI restart button (and restart
  banner) now correctly waits for the engine to go DOWN before polling for
  it to come back UP. Previously, `pingEngine()` returned true immediately
  because uvicorn was still alive during graceful shutdown, causing the
  button to exit "Restarting…" state after ~2 seconds.

## [0.1.0b215] - 2026-02-22

### Changed
- **Settings UI: TOML editors redesigned.** Removed accordion wrappers from
  Agents, Speech (stt.advanced), and Audio (audio.sounds, audio.advanced) tabs.
  Editors now render immediately with a section title, no line numbers, no card
  container, and Save/Reset buttons below the editor aligned left.
- **Settings UI: Shortcuts editor redesigned.** Removed accordion wrapper —
  shortcuts are always visible with title, rows, and Save/Reset below.
- **Settings UI: Audio field ordering.** Sounds appears before Advanced in the
  Audio tab via declarative `FIELD_ORDER` in field-config.ts.

## [0.1.0b214] - 2026-02-21

### Fixed
- **Settings UI: "Key" → "Hotkey" label.** The hotkey field showed "Key" because
  `humanize()` used the last dotted segment. Added `LABEL_OVERRIDES` map in
  `field-config.ts` for declarative label customization.
- **Settings UI: Agents tab no longer wrapped in accordion.** The `agent_types`
  TOML editor now renders immediately without a toggle header via `TOML_NO_ACCORDION`.
- **Settings UI: `claim_key` visible in Agents tab.** Added `SECTION_EXTRA_FIELDS`
  to surface cross-section fields — `client.claim_key` now appears alongside
  agent type definitions.
- **Settings UI: Restart Engine button in Advanced.** A dedicated restart button
  is now always visible in Advanced sub-tabs, independent of the save-triggered
  restart banner.
- **README: fixed outdated `[agents.claude]` example** to correct `[agent_types.claude]`
  with `description` field. Removed stale TODO GIF placeholder.
- **pyproject.toml: removed duplicate `tomlkit` dependency** (kept `>=0.14.0`).

## [0.1.0b213] - 2026-02-21

### Fixed
- **Tray icon flicker on Linux eliminated.** The pystray/AppIndicator monkey-
  patch was creating a NEW temp file on every icon update, forcing AppIndicator
  to reload from a fresh path and briefly showing a fallback icon (white dots
  on black). Now uses content-based caching: each unique icon image gets ONE
  stable temp file, created once. Subsequent updates reuse the existing path
  so AppIndicator loads instantly without flicker.

## [0.1.0b212] - 2026-02-21

### Fixed
- **Tray icon flickering on Linux.** Each listening toggle generated 3 SSE
  status events (listening → playing → listening from beep playback), causing
  pystray/AppIndicator to rewrite the temp icon file 3 times. Added icon name
  deduplication: `_update_icon()` now skips the update if the icon hasn't
  actually changed, eliminating visible flicker.
- **Removed three-dots loading icon from tray.** The `dictare_loading` icon
  (microphone + three dots) was briefly visible during state transitions on
  Linux due to AppIndicator latency. Now "loading" and "restarting" states use
  the normal idle icon (yellow microphone). Consistent icon design: red =
  disconnected, yellow = idle/loading, green = listening.

## [0.1.0b211] - 2026-02-21

### Fixed
- **Tray icon stays red on Linux despite engine being connected.** Race condition:
  the SSE thread received engine status before `pystray.Icon` was created, so
  `_update_icon()` silently skipped (guard: `if not self._icon`). Then `run()`
  created the icon with the hardcoded "muted" image, ignoring the already-updated
  `self._state`. Now syncs icon to current state right after icon creation.

## [0.1.0b210] - 2026-02-21

### Fixed
- **Linux hotkey binding in serve mode.** The engine was disabling the hotkey
  listener on all platforms when running in serve mode (`with_bindings=False`).
  On Linux there is no Swift launcher — the engine must listen for the hotkey
  directly via evdev. Now enables the hotkey on Linux even in serve mode.
- **Tray SSE error logging.** The tray's SSE exception handler was silently
  swallowing all errors, making it impossible to diagnose "disconnected" state.
  Now logs the full exception with traceback.

## [0.1.0b209] - 2026-02-21

### Added
- **Configurable claim key.** The hotkey to claim a PTY agent as active voice
  target is now configurable via `[client] claim_key` in config.toml (default:
  `"ctrl+\\"`). Supports any `ctrl+<char>` combo (e.g. `"ctrl+]"`). Both
  raw-mode byte and kitty CSI u encoding are generated automatically.

## [0.1.0b208] - 2026-02-21

### Fixed
- **Double-tap hotkey now works on macOS with Swift launcher.** The SIGUSR1
  handler was calling `toggle_listening()` directly, bypassing the TapDetector
  state machine. Now routes through `on_hotkey_tap()` which feeds key_down +
  key_up into the TapDetector, giving double-tap detection (mode switch) for
  free. Single tap = toggle listening, double tap = switch agents/keyboard.

### Added
- **Detailed startup logging.** Engine logs every decision during startup at
  INFO level: config values read, state.json restored, output mode chosen,
  agent activation. Makes it easy to diagnose mode-reset issues.
- **Tray app logging.** Tray writes to the same JSONL log file as engine,
  tagged with `source: "tray"`. Logs startup, SSE status events, mode changes
  from menu and engine. Use `dictare logs --source tray` to filter.
- **`dictare logs --source` flag.** Filter log entries by source process
  (`engine`, `tray`). Default shows all sources interleaved by timestamp.

## [0.1.0b207] - 2026-02-21

### Fixed
- **Ctrl+\\ now works with Claude Code (kitty keyboard protocol).** Claude Code
  enables the kitty keyboard protocol (CSI u), which encodes Ctrl+\\ as the
  7-byte sequence `ESC[92;5u` instead of the standard `0x1c` byte. The stdin
  reader now detects both variants, so Ctrl+\\ claims the agent regardless of
  what keyboard protocol the child process enables.

## [0.1.0b206] - 2026-02-21

### Fixed
- **Log all ESC/0x1c stdin bytes for keyboard debug.** Temporary diagnostic
  logging to identify how terminal emulators encode Ctrl+\\ when child
  processes change the keyboard protocol.

## [0.1.0b205] - 2026-02-21

### Fixed
- **Enhanced Ctrl+\\ diagnostic logging.** Session log now records both
  `raw_0x1c_found` (raw byte detection) and `ctrl_backslash` (interception)
  events to pinpoint where the keystroke gets lost.

## [0.1.0b204] - 2026-02-21

### Fixed
- **Add diagnostic logging for Ctrl+\\.** Session log now records
  `ctrl_backslash` events to debug why the keystroke isn't reaching
  the engine on some setups.

## [0.1.0b203] - 2026-02-21

### Fixed
- **Ctrl+\\ now auto-switches to agents mode.** When pressing Ctrl+\\ to claim an
  agent, the engine also switches from keyboard to agents mode if needed.
  Previously the agent was set as current but output stayed in keyboard mode.

## [0.1.0b202] - 2026-02-21

### Added
- **Ctrl+\\ to claim agent.** Press Ctrl+\\ in any `dictare agent` terminal to
  make that agent the active voice target. No mouse tracking, no terminal
  interference — just a single keystroke to redirect voice input.

## [0.1.0b201] - 2026-02-21

### Fixed
- **Input Monitoring: try `open` to launch as real macOS app.** Using `open`
  instead of running the binary directly gives Dictare.app its own TCC
  identity (not Terminal's), which may trigger the automatic macOS prompt.
  Falls back to opening System Settings if the prompt doesn't appear.

## [0.1.0b200] - 2026-02-21

### Fixed
- **Input Monitoring setup actually works now.** `CGRequestListenEventAccess()`
  returns true on Sequoia even when permission is NOT granted (same broken API
  pattern).  Replaced with marker-file approach: on first install (or after
  launcher recompilation), always opens System Settings to Input Monitoring
  with clear instructions.  Subsequent installs with the same binary skip.

## [0.1.0b199] - 2026-02-21

### Fixed
- **Input Monitoring setup fallback.** `CGRequestListenEventAccess()` silently
  fails on Sequoia.  When it fails, `dictare service install` now opens System
  Settings to the Input Monitoring page with clear instructions to add Dictare.app.

## [0.1.0b198] - 2026-02-21

### Added
- **Automatic Input Monitoring permission request during service install.**
  `dictare service install` now calls `CGRequestListenEventAccess()` via the
  Swift launcher before loading the service.  macOS shows a system dialog on
  first install — the user approves and the hotkey works immediately.

## [0.1.0b197] - 2026-02-21

### Fixed
- **Double toggle on hotkey tap from Swift launcher.** The engine's pynput
  hotkey listener was active even in serve mode, catching the same Right Cmd
  keypress that the Swift launcher already handles via CGEventTap + SIGUSR1.
  Now `hotkey_enabled=False` in serve mode — only SIGUSR1 toggles listening.

## [0.1.0b196] - 2026-02-20

### Fixed
- **Hotkey stops working after a while — CGEventTap re-enable.** macOS
  disables CGEventTap after a timeout (`tapDisabledByTimeout`) or system
  event (`tapDisabledByUserInput`).  The callback now detects these events
  and re-enables the tap immediately, so the hotkey keeps working.

## [0.1.0b195] - 2026-02-20

### Fixed
- **Revert `CGPreflightListenEventAccess()` — unreliable from launchd on
  Sequoia** (always returns false even when Input Monitoring IS granted, same
  class of bug as `AXIsProcessTrusted()`).  Back to using `CGEvent.tapCreate()`
  return value as the sole indicator: nil = no permission, non-nil = works.
  This was the proven approach from the PoC.

## [0.1.0b194] - 2026-02-20

### Fixed
- **Input Monitoring detection uses `CGPreflightListenEventAccess()`.** On Sequoia,
  `CGEvent.tapCreate()` succeeds even without Input Monitoring permission — the tap
  is created but silently receives no events, causing a false "active" hotkey status.
  Now the launcher checks `CGPreflightListenEventAccess()` first and writes "failed"
  immediately if the permission is not granted. Also added `input_monitoring` to the
  `--check-permissions` JSON output.

## [0.1.0b193] - 2026-02-20

### Fixed
- Clean stale `~/.dictare/hotkey_status` during orphan kill so the new
  launcher reports fresh Input Monitoring state instead of inheriting
  the old "active" value from a killed process.

## [0.1.0b192] - 2026-02-20

### Fixed
- **Service install kills orphan processes from previous versions.** The b191
  fix only worked for NEW launchers — when upgrading from pre-b191, the OLD
  `stop()` ran (without kill verification), leaving the old process alive.
  `install()` now always runs `_kill_orphan_processes()` which reads the engine
  PID file (`~/.dictare/engine.pid`) and pkills the Dictare.app launcher binary,
  regardless of launchd state.

## [0.1.0b191] - 2026-02-20

### Fixed
- **Service stop/restart now reliably kills the old process.** Root cause: the
  Swift launcher's C `signal()` handlers didn't fire inside `NSApplication.run()`'s
  main thread, so `launchctl unload` (SIGTERM) left the old process alive. Fix:
  replaced C signal handlers with GCD `DispatchSource` (integrates with the run
  loop) and added `applicationShouldTerminate` delegate method for clean child
  termination. Python-side `stop()` now reads the PID before unloading, waits up
  to 3 seconds, and escalates to SIGKILL if the process survives.

## [0.1.0b190] - 2026-02-20

### Added
- **Tray shows Input Monitoring warning** when permission is missing (macOS).
  Red icon + menu item with warning symbol that opens System Settings directly.
- Swift launcher writes `~/.dictare/hotkey_status` ("active" or "failed")
  so the Python engine can report Input Monitoring state to the tray.

## [0.1.0b189] - 2026-02-20

### Fixed
- **Global hotkey works from launchd service (macOS Sequoia).** Root cause:
  CGEventTap created by a Python process spawned by launchd never receives
  events on Sequoia — the tap is created but non-functional. Fix: move the
  CGEventTap to the Swift launcher (Dictare.app), which runs as an
  NSApplication with `.accessory` activation policy. The launcher detects
  Right Cmd taps and sends SIGUSR1 to the child Python engine, which toggles
  listening. Requires Dictare.app to be granted both **Accessibility** and
  **Input Monitoring** in System Settings.

### Changed
- Removed Python.app binary detection and PYTHONPATH injection from launchd
  install — no longer needed since the Swift launcher handles the hotkey.
- `generate_plist()` no longer accepts `pythonpath` parameter.

## [0.1.0b188] - 2026-02-20

### Fixed
- **Restore `AXIsProcessTrustedWithOptions` call in Swift launcher** (with
  `prompt: false`). This call activates the accessibility trust context in
  the parent process; without it, child processes (Python/pynput) cannot
  create a working CGEventTap. No dialog is shown — user grants Accessibility
  via System Settings if needed.

## [0.1.0b187] - 2026-02-20

### Fixed
- **Service crash: `No module named dictare`** — b186 used the Python.app binary
  but forgot to inject PYTHONPATH (the .app binary is outside the venv and can't
  find installed packages). Restored PYTHONPATH injection in the launchd plist
  pointing to the venv's site-packages.

## [0.1.0b186] - 2026-02-20

### Fixed
- **Hotkey works again from launchd service.** b185 regressed the hotkey by
  removing the Python.app binary detection. Brew Python ships two separate
  binaries with different inodes and different TCC identities:
  `bin/python3.11` (CLI) and `Python.app/.../Python` (the one shown as "Python"
  in Accessibility / Input Monitoring). The service was spawning the CLI binary,
  which is NOT in TCC — pynput's CGEventTap silently failed.
  New `_find_framework_python_app()` derives the `.app` binary from the
  framework directory structure (works for any framework Python, not just brew).
- **`create_app_bundle` updates `python_path` without recompiling the launcher**
  when only the path changed. Previously any path change triggered a full bundle
  recreation, which invalidated macOS TCC trust.

## [0.1.0b185] - 2026-02-20

### Fixed
- **Remove misleading Accessibility permission checks and prompts.** macOS Sequoia
  does not allow `CGEventTap` in launchd-spawned processes — `AXIsProcessTrusted()`
  always returns False regardless of TCC entries. This caused: (1) the Swift launcher
  to show the macOS permission dialog on every engine restart, (2) the tray to show a
  red "Grant Accessibility Permission" item even when the user had granted it, (3) the
  b183/b184 brew Python.app swap logic to run needlessly. The global hotkey only works
  from a foreground Terminal session (`dictare serve`); when running as a service, users
  toggle listening via the tray menu.
- Removed `AXIsProcessTrustedWithOptions` call from Swift launcher (no more dialog).
- Removed `_check_ax_direct()` from `permissions.py` — accessibility always True.
- Removed "Grant Accessibility Permission" from tray menu.
- Removed `_find_brew_python_app()` and `_is_ax_trusted()` from `launchd.py`.
- Simplified `install()` — no more Python binary swap or PYTHONPATH injection.
- Removed `pythonpath` parameter from `generate_plist()`.

## [0.1.0b184] - 2026-02-20

### Fixed
- **`dictare service install` is now idempotent** — removed the "already installed"
  early-exit guard that prevented the b183 brew-Python-app fix from taking effect when
  the service was already installed. `service install` always rewrites the plist/unit
  and reloads the service.
- **`launchd.install()` unloads before reloading** so the updated plist takes effect
  even when the service is already running.

## [0.1.0b183] - 2026-02-20

### Fixed
- **macOS service now uses brew Python.app when current Python is not TCC-trusted.**
  When `dictare service install` is run from a uv-managed venv (standalone CPython
  binary with no `.app` bundle), the engine's `python_path` is automatically swapped
  to the brew Python.app binary (`/opt/homebrew/Cellar/python@3.11/.../Python.app`),
  which ships as a proper macOS `.app` bundle and is already trusted in TCC on most
  developer systems. The venv's `site-packages` are injected via `PYTHONPATH` in the
  launchd plist so all installed packages (including the editable dictare install)
  remain accessible. This allows pynput's `CGEventTap` to succeed, making the push-to-
  talk hotkey work from the launchd service.
- **`permissions.py` accessibility check now uses Python-direct ctypes call** instead of
  the Dictare.app subprocess approach. The subprocess check (`Dictare --check-permissions
  → AXIsProcessTrusted()`) gave wrong results in a launchd agent context: spawned
  subprocesses lack a window-server session, so `AXIsProcessTrusted()` in the subprocess
  returned `false` even for a genuinely trusted binary. Checking directly via ctypes in
  the engine process is the authoritative answer (it's the same process that runs pynput).
  Microphone still checked via the launcher (Dictare.app registered with AVFoundation).

## [0.1.0b182] - 2026-02-20

### Fixed
- **`linux-install.sh` now delegates to `dictare service install`** instead of
  writing the systemd unit file inline with a hardcoded `ExecStart`. The inline
  version still had `python -m dictare engine start` (removed in b179), causing
  the Linux service to fail with exit code 2 on every start.
- **`systemd.py`** unit template now includes `PYTHONUNBUFFERED=1` and the correct
  `GI_TYPELIB_PATH` for the host architecture (x86_64, aarch64, arm, riscv64).
  Previously these were only set in `linux-install.sh`; now any `dictare service install`
  generates the correct environment regardless of how it's invoked.

## [0.1.0b181] - 2026-02-20

### Fixed
- **`_find_launcher` now checks service-installed bundle first** (`~/Applications/Dictare.app`).
  The brew Cellar path was checked first but has a different TCC identity — calling
  `AXIsProcessTrusted()` from it returns `false` in a launchd service context where the
  Terminal session is not present. The service-installed bundle is the one the user
  granted Accessibility permission to, so it must be checked first.
  Fixes `accessibility: false` in `/status` and fixes hotkey not working after the engine
  runs as a launchd service.

## [0.1.0b180] - 2026-02-20

### Fixed
- **Tray no longer prompts for Accessibility permission.** The tray process does not need
  Accessibility — the engine (running inside `Dictare.app` via the Swift launcher) handles
  all keyboard injection and hotkey listening. The tray reads permission state from the
  engine's `/status` endpoint. Removed `_ensure_accessibility()` from tray startup.
- **`create_app_bundle` skips recreation when bundle is unchanged** (same Python path +
  launcher binary). Recreating the `.app` binary invalidates macOS TCC trust, causing
  repeated Accessibility permission dialogs after reinstall.
- **`is_accessibility_granted()` now reports Dictare.app's trust, not Python's.** Calls
  `Dictare --check-permissions` (Swift launcher) which runs `AXIsProcessTrusted()` from
  the bundle's process context. Falls back to ctypes for dev/non-bundle environments.

## [0.1.0b179] - 2026-02-20

### Changed (breaking)
- **`dictare engine` subcommand group removed entirely.** Use `dictare serve` instead.
  - `dictare engine start` → `dictare serve`
  - `dictare engine start -d` → `dictare service install` (for service) or `dictare serve` (for dev)
  - `dictare engine stop` → `dictare service stop`
  - `dictare engine status` → `dictare service status`
- **`dictare serve`** is now a top-level command (Ollama-style). Runs in foreground and logs
  to both the JSONL file (`~/.local/share/dictare/logs/engine.jsonl`, used by `dictare logs -f`)
  and stdout (captured by systemd/launchd; visible in terminal during dev). `--verbose` enables
  DEBUG-level output. The service manager handles backgrounding and `Restart=always`.
- Service templates updated: systemd `ExecStart` and launchd plist fallback now call
  `dictare serve` instead of `dictare engine start -d`.
- Swift launcher (macOS .app bundle) updated to call `dictare serve`.
- `engine.restart` protocol command simplified: no longer spawns a bootstrap subprocess
  (which broke systemd/launchd PID tracking). Now just exits; the service manager restarts.
- Homebrew formula: removed `service do` block. Service is managed via `dictare service install`,
  not `brew services`. Caveats updated accordingly.
- `scripts/macos-install.sh`: replaced `brew services start/stop` with `dictare service start/stop`.

## [0.1.0b178] - 2026-02-20

### Fixed
- Tray: removed "try brew services first" fallback from `_on_restart_engine()`. The tray
  now always uses the native service backend (`launchd` on macOS, `systemd` on Linux),
  which manages `com.dictare.engine` — the same label used by `dictare service install`.
  Previously the tray would silently restart via `homebrew.mxcl.dictare` if brew was
  managing the service, creating two separate launchd entries with different labels and
  causing confusion about which service was actually running.

## [0.1.0b177] - 2026-02-20

### Added
- Engine: new `engine.restart` protocol command that saves state, then spawns a detached
  bootstrap subprocess which waits for the current engine PID to exit and starts a fresh
  instance via `dictare engine start -d`. This makes "Restart Engine" in the web UI work
  correctly even when the engine was started manually or via the tray (not via the service
  manager). Includes a 6-second watchdog that exits with code 0 (avoiding double-start when
  `Restart=always` is active).
- Web UI: `restartEngine()` now sends `engine.restart` instead of `engine.shutdown`, so
  the engine always comes back after clicking Restart — regardless of how it was started.

## [0.1.0b176] - 2026-02-20

### Fixed
- Engine: state (listening/agent/mode) is now saved to disk before shutdown so restart
  restores the exact pre-restart state. Previously `_persist_state()` was skipped during
  shutdown (because `_running=False`), leaving a stale `listening=true` in the state file
  even when the engine was idle — causing every "Restart Engine" to come back in listening mode.
- Engine: shutdown watchdog now exits with code 1 (was 0) so `Restart=on-failure` systemd
  services (pre-b171 install) also restart after a hung shutdown, not just `Restart=always`.

## [0.1.0b175] - 2026-02-20

### Fixed
- Tests: `_run_daemon` tests now redirect log output to `tmp_path` instead of the
  production log file (`~/.local/share/dictare/logs/engine.jsonl`). Previously
  running `pytest` would inject test entries (PID paths, mock state, etc.) into
  the user's live log stream visible via `dictare logs -f`.
  Added `_reset_dictare_logger` autouse fixture to restore logger handlers after
  each daemon test, preventing handler leakage across test modules.

## [0.1.0b174] - 2026-02-20

### Fixed
- state.py: demote "Failed to load state" from WARNING to DEBUG (expected fallback)
- accessibility.py: demote "Could not check Accessibility permission" from WARNING
  to DEBUG (ctypes OSError in test env is not a real error)

## [0.1.0b173] - 2026-02-20

### Fixed
- Engine: shutdown watchdog — if `stop()` hangs (e.g. audio deadlock during restart), a daemon
  thread force-exits the process after 6 s so launchd/systemd can restart it cleanly
- Engine: duplicate PID file write in `_run_daemon` caused `engine start -d` to fail immediately
  with "already running" after `kill -9` (the PID was written before `_check_single_instance()`
  ran, which then found its own PID and refused to start)
- Settings: all config changes via web UI are now logged (`settings.change key=… value=…`)
- Settings UI: `agent_types` no longer appears in the General tab (it's a dict/complex field
  that belongs to the Agents tab; General now only shows top-level scalar fields)

## [0.1.0b172] - 2026-02-20

### Added
- Settings UI: permanent "Engine" section at the bottom of the Advanced tab with a
  "Restart Engine" button — always available without needing to save settings first
- Settings UI: after clicking "Restart Engine" (from either the banner or the new section),
  the banner shows "Engine is restarting…" and polls `/status` every 1.5 s; when the engine
  comes back online, the page reloads automatically and the banner disappears

## [0.1.0b171] - 2026-02-20

### Fixed
- Linux: systemd service now uses `Restart=always` instead of `Restart=on-failure`; previously
  a clean shutdown (exit code 0) — such as clicking "Restart Engine" in the web UI — would not
  trigger a service restart on Linux (only crashes did). Now any exit restarts the engine.
  Added `StartLimitIntervalSec=60` / `StartLimitBurst=5` in `[Unit]` to prevent infinite restart
  loops when the engine fails repeatedly at startup.
- Both `scripts/linux-install.sh` and `dictare service install` (via `daemon/systemd.py`) updated.

## [0.1.0b170] - 2026-02-20

### Fixed
- Engine: enforce single instance via PID file (`~/.dictare/engine.pid`); starting a second
  engine while one is already running now fails immediately with a clear error message
- Engine: hard-exit if HTTP server fails to bind the port (e.g. port already in use); previously
  the engine would continue running without an HTTP server, silently grabbing the microphone
  alongside an existing instance — causing the dual-output bug (one engine typed via keyboard,
  another sent to agents)

## [0.1.0b169] - 2026-02-20

### Fixed
- Linux: symlink `dictare` to `~/.local/bin` so the command works from any shell after install

## [0.1.0b168] - 2026-02-20

### Fixed
- Parakeet: on Linux, allow onnxruntime to pick providers automatically (CUDA if available)
  Previously forced CPUExecutionProvider everywhere — now only forced on macOS where CoreML
  crashes with ONNX external data files

## [0.1.0b167] - 2026-02-20

### Changed
- Default STT model changed from `large-v3-turbo` to `parakeet-v3`
  - Better quality on European languages (Italian, German, Spanish, French, ...)
  - Similar size (~670 MB vs ~800 MB for large-v3-turbo)
  - Runs on CPU via ONNX — no MLX/CUDA required

## [0.1.0b166] - 2026-02-20

### Added
- Contract tests for onnx-asr API (`tests/test_onnx_asr_contract.py`) — catch API assumption
  errors without downloading model weights (runs in 0.08s)

## [0.1.0b165] - 2026-02-20

### Fixed
- Parakeet transcription now works — `TextResultsAsrAdapter` API is `.recognize()`, not `.transcribe()`
- Simplified transcription path: pass numpy array directly (no temp WAV file needed)

## [0.1.0b164] - 2026-02-20

### Fixed
- Parakeet model loading now works on macOS Apple Silicon — CoreMLExecutionProvider was
  causing `[ONNXRuntimeError]: model_path must not be empty` when loading ONNX models
  with external data files (`.onnx.data`). Fix: force `providers=["CPUExecutionProvider"]`
- `stt_model_id` in log output now shows correct ID for Parakeet (`nemo-parakeet-tdt-0.6b-v3`)
  instead of wrong `mlx-community/whisper-parakeet-v3`
- Panel status now shows `ONNX` (not `MLX`) as the compute device for Parakeet engine

## [0.1.0b163] - 2026-02-20

### Fixed
- Engine startup errors now appear in `dictare logs` — previously crashed silently
  - STT/VAD loading failures: `logger.debug` → `logger.info` + `logger.error` with traceback on failure
  - Daemon startup failures: `controller.start()` exceptions now logged as ERROR before exit

## [0.1.0b162] - 2026-02-20

### Added
- `dictare logs` — human-readable log viewer
  - `dictare logs` — last 50 lines, formatted
  - `dictare logs -f` — follow (like `tail -f`)
  - `dictare logs -n 100` — last N lines
  - `dictare logs --raw` — raw JSONL (pipe-friendly, e.g. `| jq .`)
  - Falls back gracefully if engine hasn't started yet

## [0.1.0b161] - 2026-02-20

### Fixed
- `parakeet-v3` now appears in the STT model dropdown in Settings UI

## [0.1.0b160] - 2026-02-20

### Added
- **Models UI**: web-based model manager at Settings → Models
  - Lists all STT/TTS models with cache status, size, and "in use" badge
  - Download button per model with real-time progress bar (SSE stream)
  - `GET /models` — model list with cache/configured/downloading status
  - `POST /models/{model_id}/pull` — start background download
  - `GET /models/pull-progress` — SSE stream with fraction/bytes progress
- `ModelsPage.svelte` — new Svelte 5 component for model management

## [0.1.0b159] - 2026-02-20

### Changed
- `onnx-asr` promoted to mandatory dependency (was optional `[parakeet]` extra)
  - onnxruntime (~15 MB) is smaller than ctranslate2 (~30 MB, already required via faster-whisper)
  - No install friction: `model = "parakeet-v3"` works out of the box
- `ParakeetEngine`: removed guided-install UX (no longer needed, onnx-asr always present)

## [0.1.0b158] - 2026-02-20

### Changed
- `ParakeetEngine`: switched from `nemo_toolkit[asr]` (~2 GB) to `onnx-asr` (~122 kB package, no PyTorch)
- `dictare[parakeet]` optional dep is now `onnx-asr>=0.1.0` — installs in seconds, not minutes
- Model: `nemo-parakeet-tdt-0.6b-v3` (25 European languages: IT, DE, ES, FR, …, auto language detection)

### Added
- Guided install UX: when `onnx-asr` is missing and a console is available, prompts "Install now? [Y/n]"
  then runs `pip install onnx-asr` with real output. In headless/daemon mode: clear error with `dictare stt install parakeet-v3`

## [0.1.0b157] - 2026-02-20

### Added
- Parakeet V3 STT engine (`ParakeetEngine`) via NVIDIA NeMo ASR
- Model selection: `model = "parakeet-v3"` (TDT 0.6B, 25 European languages) or `"parakeet-ctc"` (CTC 1.1B)
- Optional dependency: `pip install 'dictare[parakeet]'` installs `nemo_toolkit[asr]`
- Engine auto-selection: any model name starting with `"parakeet"` routes to `ParakeetEngine`
- `is_parakeet_model()` helper for engine routing
- STT advanced template updated with Parakeet install instructions

## [0.1.0b156] - 2026-02-19

### Changed
- Sounds section template: all fields now commented out (defaults only), `volume` param added to each event

## [0.1.0b155] - 2026-02-19

### Fixed
- Codex preset: `--approval-mode full-auto` → `--dangerously-bypass-approvals-and-sandbox`
- Codex `continue_args`: `["--resume"]` → `["resume", "--last"]` (`resume` is a subcommand)

## [0.1.0b154] - 2026-02-19

### Added
- `SoundConfig.volume` (0.0–1.0): per-event playback volume control for audio feedback sounds
- Agent type presets template: sonnet, sonnet-danger, opus, opus-danger, chatgpt, chatgpt-danger

### Changed
- `_AGENT_TYPES_HEADER` and `create_default_config()` ship with ready-to-use presets (previously comment-only examples)

## [0.1.0b153] - 2026-02-19

### Fixed

- **`ShortcutsField` structuredClone error** — Svelte 5 reactive proxies can't be cloned
  with `structuredClone`. Replaced with `JSON.parse(JSON.stringify(...))` everywhere.

## [0.1.0b152] - 2026-02-19

### Added

- **`ShortcutsField` structured editor** — replaces the raw TOML accordion for
  `keyboard.shortcuts` with a table of key-capture + command-dropdown rows.
  - `+ Add shortcut` appends a new row; `×` deletes a row
  - `KeyCaptureField` (shortcut mode) for the key combination column
  - Command dropdown: Toggle listening, Start listening, Stop listening,
    Next agent, Previous agent, Repeat last
  - Save/Reset enabled only when dirty; auto-dismiss "Saved" feedback
  - Accordion (collapsed by default, lazy load on first open) — same UX as TOML sections
- **`GET /settings/shortcuts`** — returns `{shortcuts: [{keys, command}]}` JSON
- **`POST /settings/shortcuts`** — accepts JSON list, validates, serializes to TOML and saves
- **`shortcuts_to_toml()`** helper in `toml_sections.py`

### Changed

- `keyboard.shortcuts` removed from `TOML_EDITABLE_KEYS` — replaced by `ShortcutsField`

## [0.1.0b151] - 2026-02-19

### Added

- **Engine-side hotkey capture** — `POST /control {"command": "hotkey.capture"}` blocks until
  the next physical key press and returns its evdev name. Works because the engine's global
  keyboard listener intercepts the key before the browser ever sees it.
  - `PynputHotkeyListener.capture_next_key()` — intercepts next `_handle_press`, converts
    pynput key to evdev name via reverse `_EVDEV_MAP`, signals a `threading.Event`
  - `EvdevHotkeyListener.capture_next_key()` — same via `evdev.ecodes.KEY` lookup in the
    existing event loop
  - `Engine.capture_next_hotkey()` — delegates to the active listener
  - `KeyCaptureField` evdev mode now calls `captureHotkey()` API instead of `window.onkeydown`
    (shortcut mode still uses browser keydown since modifier combos aren't intercepted)
  - ESC returns `KEY_ESC` which is treated as cancel (no change)

### Changed

- **Restart banner auto-dismisses** — after clicking "Restart Engine", polls `ping` every 1 s
  until the engine responds, then hides the banner automatically.
- **Keyboard tab is a single flat page** — removed Hotkey/Shortcuts sub-navigation.
  The page now shows `hotkey.key` (capture widget) followed by the Shortcuts TOML accordion.

## [0.1.0b150] - 2026-02-19

### Changed

- **`server.enabled` removed** — field was dead code (server always starts unconditionally).
  `ServerConfig` now only has `host` and `port`.
- **`server.host` UI** — right-aligned text input, width narrowed to `w-24`.
- **`pipeline.submit_filter` template** — added all supported languages (es, de, fr, pt, ja, zh, ko, ru);
  was showing only `en` + `it` which leaked developer nationality.
- **`StringField` accepts `align` prop** — `"left"` (default) or `"right"`.
  `FieldRenderer` drives it from `RIGHT_ALIGN_FIELDS`.

## [0.1.0b149] - 2026-02-19

### Added

- **`KeyCaptureField` — key capture widget** for hotkey and shortcut fields.
  Two modes driven by a `format` prop:
  - `"evdev"`: captures a single physical key → stores as `KEY_RIGHTMETA`,
    `KEY_SCROLLLOCK`, `KEY_F12`, etc. Used for `hotkey.key`.
  - `"shortcut"`: captures a modifier + key combination → stores as
    `shift+enter`, `ctrl+enter`, etc. Used for `output.submit_keys` and
    `output.newline_keys`.
  Click "Capture", press the key/combination, ESC to cancel.
  Displays a human-friendly label (`Right ⌘`, `⇧ Return`, etc.) instead of
  the raw evdev/shortcut string.

## [0.1.0b148] - 2026-02-19

### Changed

- **TOML editors are now accordions** — collapsed by default, lazy-loaded on
  first open. Applies to all TOML sections (agent_types, audio.advanced,
  audio.sounds, stt.advanced, keyboard.shortcuts, pipeline filters).
- **Save/Reset disabled when not dirty** — buttons only enable when the editor
  content differs from the last saved value; comparison on every keystroke.
- **Hide `hotkey.device` from UI form** — field still works via config file
  (Linux evdev power users), but no longer shown in the settings panel.

## [0.1.0b147] - 2026-02-19

### Added

- **`repeat` shortcut command** — resends last transcription to current agent.
  Useful when the agent UI misses keyboard input. Works independently of
  listening state. `engine.resend_last()` → `controller.repeat_last()` →
  shortcut `command = "repeat"`.

### Changed

- **Shortcut command names renamed** (breaking):
  - `project-next` → `next-agent`
  - `project-prev` → `prev-agent`
  - `switch-to-project` → `switch-to-agent`
  - `switch-to-project-index` → `switch-to-agent-index`
- **Removed dead commands**: `switch-mode`, `clear`, `cancel`, `discard`
  (never implemented; removed from `_BindingCommands` and template)
- **Shortcuts template** updated to only document real commands with examples

## [0.1.0b146] - 2026-02-19

### Fixed

- **audio.advanced template**: now starts with actual `[audio.advanced]` header
  and includes all 6 options commented out with defaults — visible in TOML editor
- **stt.advanced template**: same fix — starts with `[stt.advanced]` header
- **audio.sounds template**: replaced generic docs with actual `[audio.sounds.*]`
  entries (`enabled = true`, `# path = ""`), default bundled filenames in
  comments. Removed wrong reference to `[audio]` for advanced settings.
- **`create_default_config()` template**: updated `[stt]` block to only show
  user-facing fields; added `# [stt.advanced]` comment block

## [0.1.0b145] - 2026-02-19

### Changed (breaking)

- **`stt.advanced` sub-model** — low-level STT fields moved from `[stt]` into
  `[stt.advanced]`: `device`, `compute_type`, `beam_size`, `hotwords`,
  `max_repetitions`. User-facing fields remain in `[stt]`: `model`, `language`,
  `translate`, `hw_accel`. Edit advanced settings via Settings > STT Advanced.
- **`owned_toplevel` removed from line scanners** — `_extract_section_lines`
  and `_strip_section_lines` are now simpler: they only track section headers,
  no special-casing for top-level floating keys.
- Config file cleaned: `pre_buffer_ms = 1000` moved to `[audio.advanced]`,
  `[agent_types]` with `default` key added, stale duplicate comment blocks
  removed.

## [0.1.0b144] - 2026-02-19

### Changed (breaking)

- **`default_agent_type` removed from top-level config** — moved inside
  `[agent_types]` as `default = "claude"`. New TOML structure:
  ```toml
  [agent_types]
  default = "claude"

  [agent_types.claude]
  command = ["claude"]
  ```
- `Config.agent_types` type changed from `dict[str, AgentTypeConfig]` to
  `AgentTypesConfig` (Pydantic model with `extra="allow"`).
  Access: `config.agent_types.default`, `config.agent_types.get("claude")`,
  `config.agent_types.entries()`, `config.agent_types.items()`.
- `toml_sections.py`: `owned_toplevel` for `agent_types` is now empty — the
  scanner is simpler, no special-casing for a floating top-level key.

## [0.1.0b143] - 2026-02-19

### Fixed

- **TOML editor duplicate-comments bug**: saving a section repeatedly caused
  comment blocks to accumulate in the file on every save. Root cause: tomlkit
  leaves orphaned comments when deleting keys. Fix: replaced tomlkit-based
  deletion in `_write_section_raw` with a line scanner (`_strip_section_lines`)
  that is the symmetric inverse of `_extract_section_lines` — comments
  preceding an owned header are removed together with it.
- **audio.advanced showed [object Object]**: `list_config_keys()` emitted
  `type="AudioAdvancedConfig"` for nested Pydantic sub-models instead of
  `"dict"`, causing ComplexField to render instead of the TOML editor.
  Fixed to use `"dict"` for any `BaseModel` instance value.
- Rebuilt UI (`src/dictare/ui/dist/`) to include audio.advanced TOML editor.

### Added

- `tests/test_toml_sections.py`: regression tests for strip/extract symmetry
  and idempotency (saving same content N times doesn't grow the file).

## [0.1.0b142] - 2026-02-19

### Changed

- **Breaking config change**: Advanced audio parameters moved from `[audio]` to
  `[audio.advanced]` subsection (`sample_rate`, `channels`, `device`,
  `pre_buffer_ms`, `min_speech_ms`, `transcribing_sound_min_ms`).
  Introduced `AudioAdvancedConfig` Pydantic sub-model inside `AudioConfig`.
- Settings UI: `[audio.advanced]` is now a dedicated TOML editor section
  (pure WYSIWYG), visible in the Audio settings page.
  Child fields (`audio.advanced.*`) are auto-hidden from the form via the
  generic `isHiddenByParentToml` pattern — scales to any future `.advanced`
  sections without code changes.
- Removed `HIDDEN_FORM_KEYS` from field-config.ts (replaced by the above
  parent-TOML logic).
- Config template updated: `[audio]` comments reflect only the form fields;
  `[audio.advanced]` block added with all 6 parameters.

## [0.1.0b141] - 2026-02-19

### Changed

- Settings UI: Audio page now shows only the commonly-changed fields in the
  form (audio_feedback, silence_ms, headphones_mode, max_duration).
  Advanced fine-tuning fields (sample_rate, channels, device, pre_buffer_ms,
  min_speech_ms, transcribing_sound_min_ms) are hidden from the form and
  accessible only via `dictare config edit` or the config.toml directly.
- The Sounds TOML editor template now includes a note pointing to the
  advanced [audio] parameters and how to edit them.
- Introduced `HIDDEN_FORM_KEYS` in field-config.ts: a single place to move
  any field between the form UI and TOML-only access.

## [0.1.0b140] - 2026-02-19

### Added

- `audio.transcribing_sound_min_ms` config field (default: 8000 ms): controls the
  minimum audio duration before the typewriter sound plays during transcription.
  Previously hardcoded at 8 s; now visible and adjustable in Settings → Audio → SOUNDS.
- Roadmap section to README: plugin architecture and realtime partial transcription.

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
- `realtime` parameter from `create_engine()` and `DictareEngine.__init__()`.
- `cli/models.py` references to removed `realtime_model` and `qwen3` engine.

## [0.1.0b139] - 2026-02-19

### Removed

- `qwen3` TTS engine: it was an LLM (Qwen3), not a TTS engine — deleted `tts/qwen3.py`,
  removed from `TTSConfig.engine` Literal, `tts/__init__.py`, `install_info.py`, and `speak.py`.
- Dead TTS phrase keys from `engine.py`: `transcription_mode`, `command_mode`, `voice` —
  superseded by the pipeline architecture. Only `agent` phrase remains.
- `daemon.preload_tts`, `daemon.preload_stt`, `daemon.idle_timeout` config fields: never
  read anywhere in the codebase; removed from `DaemonConfig` and config template.
- `src/dictare/ui/__init__.py`: phantom package (0 bytes, no imports, no purpose).
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
  `--continue` / `-C` is passed to `dictare agent`. Keeps continue syntax inside the
  agent type config (Claude uses `["-c"]`, Codex could use `["--resume"]`, etc.).
- `dictare agent <name> --type <type> --continue` / `-C` flag: continues the previous
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
- Config: updated agent_types comment to document the `dictare agent <name> --type <type>`
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
- Linux: `linux-install.sh` installs udev rule `99-dictare.rules` for evdev access —
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

- `dictare agent`: agent_id (session name) is now independent from the agent type.
  Added `--type <type>` option to select the command template from `agent_types` config.
  Without `--type`, `default_agent_type` is used. agent_id is required.
  Examples: `dictare agent frontend --type claude-sonnet`, `dictare agent frontend`
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

- **Agent type presets** — renamed `[agents.*]` → `[agent_types.*]` in config for clarity. Added `default_agent_type` field so `dictare agent` with no arguments launches the default agent. Added optional `description` field to each agent type.
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

- **Engine state persistence** — Saves active agent, output mode, and listening state to `~/.dictare/state.json`. Restores output mode and preferred agent on restart. Config option `daemon.restore_listening` (default: false) controls whether listening state is restored.
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

- **Tray icon color code** — Four distinct colors for four states: red = disconnected (server unreachable), blue = loading/restarting (connected, preparing), yellow = idle (ready), green = listening. Loading previously reused the yellow idle icon; now uses the dedicated blue `dictare_loading` icon.

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
- **Daemon has no log output** — `setup_logging()` was never called in daemon mode. Python logger had no handler, all `logger.info/warning` calls went nowhere. Now logs to `~/.local/share/dictare/logs/engine.jsonl`.
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

- **Split compliance tests into protocol and internal** — `test_openvip_protocol.py` (64 tests) contains the portable protocol compliance suite: zero dictare imports, all tests via real HTTP/SSE. Can be copied to any OpenVIP implementation's repo as an executable spec. `test_openvip_internal.py` (19 tests) contains dictare-specific tests using mock engine and TestClient. Shared infrastructure (mock classes, `live_url` fixture) moved to `conftest.py`.

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

- **Dead code cleanup (~1050 lines)** — removed legacy `DictareApp` orchestrator (`core/app.py`), `LiveStatusPanel` (`ui/status.py`), and `commands/` package (`AppCommands`, `CommandSchema`, `CommandParam`). These were from a previous architecture superseded by `AppController` + `StatusPanel` (HTTP polling). Zero references in production code or tests.

## [0.1.0b57] - 2026-02-14

### Fixed

- **Loading state stuck after engine init** — `_loading_active = False` at end of `init_components()` didn't push SSE status update, so tray and mux stayed on "loading" until the next state change. Now `_notify_http_status()` is called when loading completes.
- **Loading color inconsistency** — tray showed blue (dedicated loading icon), mux showed yellow. Both now show yellow (same as "off"/idle) — engine not ready but not disconnected.

## [0.1.0b56] - 2026-02-14

### Fixed

- **TTS dependency check for system engines** — `dictare dependencies check` now verifies that `espeak`/`say` binaries are actually installed in PATH, instead of silently skipping the check.
- **TTS default engine per platform** — default TTS engine is now `say` on macOS (built-in) and `espeak` on Linux.
- **Slow test moved to slow suite** — `test_sse_error_reports_reconnecting` (1s) marked as `@pytest.mark.slow`, excluded from default test run.

## [0.1.0b55] - 2026-02-14

### Changed

- **Unified display state resolution** — new `dictare.status.resolve_display_state()` function replaces duplicated state logic in tray and mux. Both now show consistent state names ("loading", "listening", "idle", "standby") and styles. Unicode escape sequences replaced with literal characters (`●`, `○`, `·`).

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
- **VoxType capitalization** — fixed "Dictare" → "VoxType" in tray About menu.

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

- **Pre-release cleanup** — removed dead code (`DictareError` class, unused), extracted shared `_normalize()`/`_tokenize()` from pipeline filters into `pipeline/filters/_text.py`, fixed `pyproject.toml` target-version mismatch (py310 → py311), removed redundant `typer` from dev extras. Added debug logging for partial transcription errors in engine.

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

- **Tray: Settings menu item** — opens `~/.config/dictare/config.toml` in the default editor. Uses `open -t` on macOS, `xdg-open` or `$EDITOR` on Linux.
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

- **No audio feedback on brew install** — `.gitignore` pattern `sounds/` was excluding `src/dictare/audio/sounds/*.mp3` from the sdist tarball. Changed to `/sounds/` to only ignore the root-level originals directory.

## [0.1.0b24] - 2026-02-14

### Fixed

- **Engine crash on brew install** — removed `rm_rf` of PyAV `.dylibs/` from brew formula. The hack prevented the install_name_tool warning but broke `av` at runtime (dlopen failure), causing the engine to crash in a respawn loop.

### Changed

- **`src/dictare/libs/` — pure Python replacement library** — moved `metaphone()` and `levenshtein_distance()` into `dictare.libs.jellyfish`, a drop-in module with the same interface as the external `jellyfish` package. To switch back: change `from dictare.libs.jellyfish import ...` to `from jellyfish import ...`.
- **`uvicorn[standard]` → `uvicorn`** — removed `[standard]` extras which pulled in `watchfiles` (another Rust extension with the same install_name_tool issue). `watchfiles` is only used for `--reload` in development, not needed in production.

### Removed

- **jellyfish dependency** — replaced with pure Python in `dictare.libs.jellyfish`. The jellyfish Rust extension (`_rustyfish.so`) caused Homebrew's `install_name_tool` to fail with "header too small" during `brew install`.

## [0.1.0b23] - 2026-02-13

### Removed

- **jellyfish dependency** — replaced with pure Python `_metaphone()` and `_levenshtein_distance()` in `agent_filter.py`. The jellyfish Rust extension (`_rustyfish.so`) caused Homebrew's `install_name_tool` to fail with "header too small" during `brew install`. Since these functions are only called on short agent names during occasional voice commands (not a hot path), the pure Python implementation has no meaningful performance impact.

## [0.1.0b20] - 2026-02-13

### Added

- **Microphone permission support** — Swift launcher now requests mic permission (shows "Dictare" in dialog). `NSMicrophoneUsageDescription` added to Info.plist. Without this, macOS silently feeds zeros to the audio stream.
- **Microphone permission in `/status`** — new `platform.permissions.microphone` field. Tray shows "Grant Microphone Permission" menu item when not granted, clicking opens System Settings → Microphone directly.
- **`dictare.platform.microphone` module** — `is_microphone_granted()` (cached 5s) and `open_microphone_settings()`.

### Fixed

- **Brew `post_uninstall` cleanup** — now removes Accessibility TCC entry via `tccutil reset`.

## [0.1.0b19] - 2026-02-13

### Added

- **macOS .app bundle via Homebrew** — `brew install` now creates `/Applications/Dictare.app` so macOS shows "Dictare" (not "Python") in mic indicator, Accessibility settings, and Activity Monitor.
- **Accessibility permission in `/status`** — new `platform.permissions.accessibility` field reports whether Accessibility is granted. Tray shows "Grant Accessibility Permission" menu item when missing, clicking opens System Settings directly.
- **Shared accessibility utility** — `dictare.platform.accessibility` module with `is_accessibility_granted()`, `request_accessibility()`, `open_accessibility_settings()`. Cached (5s TTL) for polling efficiency.

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

- **Zero-config post-install** — both `brew install` and `curl | bash` produce a ready-to-use install. No extra commands needed: just `dictare agent claude`. Models auto-download on first engine start, service is managed automatically.
- **`dictare setup` skips service if Homebrew is active** — detects `brew services` and avoids creating a duplicate plist.
- **Simplified Homebrew caveats** — removed `dictare setup` instruction; models download automatically.

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

- **`install.sh`** — `curl | bash` installer (Ollama-style): detects OS, installs uv + dictare, runs setup wizard. Supports `--skip-setup` and `--uninstall`.
- **`scripts/publish.sh`** — interactive PyPI publish workflow: tests, builds + uploads openvip then dictare, creates GitHub release. Supports `--dry-run`.

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

- **`dictare setup`** — first-time wizard: creates config, downloads models, installs service, prompts Accessibility permission.
- **Auto-pull models at engine start** — missing models are downloaded automatically instead of exiting with an error.

## [0.1.0b11] - 2026-02-13

### Changed

- **Tray icons: colored circle + white mic** — state conveyed by background color (green=listening, yellow=idle, blue=loading, red=disconnected) using approved SVG mic design. Monkey-patched pystray for crisp Retina rendering (NSImage at @2x pixels with point-size declaration).

## [0.1.0b10] - 2026-02-13

### Fixed

- **Tray icon adapts to dark/light menu bar** — pystray ignores `template=True`, so the NSImage was never marked as template. Monkey-patched `_assert_image` to call `setTemplate_(True)`. Icons regenerated at correct 18x18 @1x / 36x36 @2x size per Apple HIG.

## [0.1.0b8] - 2026-02-13

### Fixed

- **Agent starts without engine** — `dictare agent` no longer blocks with an error if the engine is not running. It starts immediately showing "connecting..." in the status bar and reconnects automatically when the engine becomes available.

### Changed

- **Redesigned icons** — circular background (was rounded square), mic centered at 75% fill, gap below base filled. SVG versions added alongside PNGs.
- **Tray hides from Dock** — `_hide_dock_icon()` sets `NSApplicationActivationPolicyAccessory` so only the tray icon shows, no Dock tile.

### Added

- **`scripts/generate_icons.py`** — generates all icon assets (SVG + PNG tray icons, `.icns` app icon).
- **`scripts/brew-rebuild.sh`** — automates sdist build → formula SHA update → `brew reinstall`.
- **Homebrew `post_uninstall` cleanup** — `brew uninstall dictare` now stops the tray, unloads the LaunchAgent, and removes the `.app` bundle automatically.
- **Homebrew caveats** — `brew info dictare` shows service/tray start instructions.

## [0.1.0b7] - 2026-02-13

### Fixed

- **Mic indicator shows "Dictare" instead of "Python"** — the .app bundle launcher script was using `exec` which replaced the bash process with python, causing macOS to attribute mic access to "Python". Now runs python as a child process so the .app bundle identity is preserved.

## [0.1.0b6] - 2026-02-13

### Fixed

- **Service stop now actually stops** — `dictare service stop` was using `launchctl stop` which only killed the process, but `KeepAlive: true` in the plist caused launchd to restart it immediately. Now uses `launchctl load/unload` to properly register/unregister the agent. Stop means stop.
- **Service status shows loaded state** — `dictare service status` now distinguishes between "running", "stopped (service not loaded)", and "not installed".
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

- **macOS .app bundle** — `dictare service install` creates `/Applications/Dictare.app` so macOS shows "Dictare" with icon in Accessibility / Input Monitoring settings.
- **Tray icons** — green mic (listening), blue (idle), orange (loading), red (muted) PNG icons for the system tray.
- **App icon** — `.icns` bundle icon with green microphone design.

## [0.1.0b2] - 2026-02-12

### Fixed

- Replace deprecated `typer-slim[standard]` dependency with `typer` (v0.23.0 removed the `standard` extra).
- Fix PyPI classifiers: "Beta" status, remove unsupported Python 3.10/3.12.

### Added

- **Homebrew tap** — `brew install dragfly/dictare/dictare`.

## [0.1.0b1] - 2026-02-12

First public beta release.

### Added

- **Voice engine** with Faster Whisper STT, Silero VAD, and configurable TTS (Piper, MLX Audio).
- **OpenVIP protocol** — HTTP API for voice interaction: `/status`, `/control`, `/speech`, SSE agent messaging.
- **Agent multiplexer** (`dictare agent claude`) — PTY-based session with merged stdin + voice input via SSE.
- **Single-command launch** — agent templates in config: `[agents.claude] command = ["claude"]`.
- **System service** — `dictare service install/start/stop/status` via launchd (macOS) / systemd (Linux).
- **Status panel** — Rich Live TUI showing model loading progress, STT state, agents, hotkey info.
- **Status bar** — persistent last-row indicator (listening/standby/reconnecting) in agent sessions.
- **Session logging** — JSONL session files in `~/.local/share/dictare/sessions/` with keystroke tracking.
- **Pipeline architecture** — filters (AgentFilter, InputFilter) and executors (InputExecutor, AgentSwitchExecutor) with PipelineLoader DI.
- **Hotkey support** — tap to toggle listening, double-tap to switch agent (evdev on Linux, pynput on macOS).
- **Multi-agent switching** — voice-activated agent switching with phonetic matching (jellyfish).
- **Hardware auto-detection** — CUDA, MLX (Apple Silicon), CPU fallback with automatic compute type selection.
- **Audio feedback** — configurable sounds for start/stop/transcribing/ready/sent events.
- **Tray app** — system tray icon with status polling and quick controls.
- **OpenVIP SDK integration** — all client-side HTTP uses `openvip.Client` (subscribe, get_status, speak, control).
- **CLI**: `dictare engine start/stop/status`, `dictare agent`, `dictare speak`, `dictare listen`, `dictare config`, `dictare service`, `dictare dependencies`.
