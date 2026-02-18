export type PresetOption = string | { value: string; label: string };

/** Fields rendered as read-only 'Edit in config file' */
export const COMPLEX_KEYS = new Set(["agent_types", "audio.sounds", "keyboard.shortcuts", "pipeline.agent_filter", "pipeline.submit_filter"]);

/** Fields rendered as TOML textarea with syntax highlighting */
export const TOML_EDITABLE_KEYS = new Set(["agent_types", "audio.sounds", "keyboard.shortcuts", "pipeline.agent_filter", "pipeline.submit_filter"]);

/** Fields with preset dropdown + custom input */
export const FIELD_PRESETS: Record<string, PresetOption[]> = {
  "stt.language": [{ value: "auto", label: "Auto-detect" }, { value: "en", label: "English" }, { value: "it", label: "Italian" }, { value: "es", label: "Spanish" }, { value: "de", label: "German" }, { value: "fr", label: "French" }, { value: "pt", label: "Portuguese" }, { value: "ja", label: "Japanese" }, { value: "zh", label: "Chinese" }, { value: "ko", label: "Korean" }, { value: "ru", label: "Russian" }],
  "stt.model": ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"],
  "stt.realtime_model": ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"],
  "tts.language": [{ value: "en", label: "English" }, { value: "it", label: "Italian" }, { value: "es", label: "Spanish" }, { value: "de", label: "German" }, { value: "fr", label: "French" }, { value: "pt", label: "Portuguese" }, { value: "ja", label: "Japanese" }, { value: "zh", label: "Chinese" }],
};

/** Input width hints: narrow | medium | normal */
export const SIZE_HINTS: Record<string, string> = {
  "audio.channels": "narrow",
  "audio.max_duration": "narrow",
  "audio.min_speech_ms": "narrow",
  "audio.pre_buffer_ms": "narrow",
  "audio.sample_rate": "narrow",
  "audio.silence_ms": "narrow",
  "client.url": "normal",
  "daemon.idle_timeout": "narrow",
  "hotkey.device": "medium",
  "hotkey.key": "medium",
  "output.newline_keys": "medium",
  "output.submit_keys": "medium",
  "output.typing_delay_ms": "narrow",
  "server.host": "medium",
  "server.port": "narrow",
  "stats.typing_wpm": "narrow",
  "stt.beam_size": "narrow",
  "stt.max_repetitions": "narrow",
  "tts.speed": "narrow",
};

/** Fields with enum/Literal types (fixed options from schema) */
export const ENUM_FIELDS = new Set(["output.mode", "stt.compute_type", "stt.device", "tts.engine"]);

