export type PresetOption = string | { value: string; label: string };

/** Fields hidden from the UI form (still configurable via config file) */
export const HIDDEN_FORM_FIELDS = new Set(["hotkey.device"]);

/** Fields whose text input should be right-aligned */
export const RIGHT_ALIGN_FIELDS = new Set(["server.host"]);

/** Fields rendered as key-capture widgets */
export const KEY_CAPTURE_FIELDS: Record<string, "evdev" | "shortcut"> = {
  "hotkey.key": "evdev",
  "output.newline_keys": "shortcut",
  "output.submit_keys": "shortcut",
};

/** Fields rendered as read-only 'Edit in config file' */
export const COMPLEX_KEYS = new Set(["agent_types", "audio.advanced", "audio.sounds", "keyboard.shortcuts", "pipeline.agent_filter", "pipeline.submit_filter", "stt.advanced"]);

/** Fields rendered as TOML textarea with syntax highlighting */
export const TOML_EDITABLE_KEYS = new Set(["agent_types", "audio.advanced", "audio.sounds", "pipeline.agent_filter", "pipeline.submit_filter", "stt.advanced"]);

/** Fields with preset dropdown + custom input */
export const FIELD_PRESETS: Record<string, PresetOption[]> = {
  "stt.language": [{ value: "auto", label: "Auto-detect" }, { value: "en", label: "English" }, { value: "it", label: "Italian" }, { value: "es", label: "Spanish" }, { value: "de", label: "German" }, { value: "fr", label: "French" }, { value: "pt", label: "Portuguese" }, { value: "ja", label: "Japanese" }, { value: "zh", label: "Chinese" }, { value: "ko", label: "Korean" }, { value: "ru", label: "Russian" }],
  "stt.model": ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo", "parakeet-v3"],
  "tts.language": [{ value: "en", label: "English" }, { value: "it", label: "Italian" }, { value: "es", label: "Spanish" }, { value: "de", label: "German" }, { value: "fr", label: "French" }, { value: "pt", label: "Portuguese" }, { value: "ja", label: "Japanese" }, { value: "zh", label: "Chinese" }],
};

/** Input width hints: narrow | medium | normal */
export const SIZE_HINTS: Record<string, string> = {
  "audio.max_duration": "narrow",
  "audio.silence_ms": "narrow",
  "client.url": "normal",
  "daemon.socket_path": "normal",
  "hotkey.device": "medium",
  "hotkey.key": "medium",
  "logging.log_file": "normal",
  "output.newline_keys": "medium",
  "output.submit_keys": "medium",
  "output.typing_delay_ms": "narrow",
  "server.host": "narrow",
  "server.port": "narrow",
  "stats.typing_wpm": "narrow",
  "tts.speed": "narrow",
  "tts.voice": "normal",
};

/** Fields with enum/Literal types (fixed options from schema) */
export const ENUM_FIELDS = new Set(["output.mode", "tts.engine"]);

/** Override the auto-generated label for specific dotted keys */
export const LABEL_OVERRIDES: Record<string, string> = {
  "hotkey.key": "Hotkey",
};

/** TOML fields rendered without accordion (always visible, no toggle header) */
export const TOML_NO_ACCORDION = new Set(["agent_types"]);

/** Extra fields to show alongside a section (cross-section visibility) */
export const SECTION_EXTRA_FIELDS: Record<string, string[]> = {
  "agent_types": ["client.claim_key"],
};

