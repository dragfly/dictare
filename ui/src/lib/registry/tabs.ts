import {
  Activity,
  AudioWaveform,
  Bot,
  HardDrive,
  Keyboard,
  Mic,
  Settings,
  SlidersHorizontal,
  Volume2,
} from "lucide-svelte";
import type { TabDef } from "$lib/types";

export const tabs: TabDef[] = [
  {
    id: "dashboard",
    label: "Dashboard",
    icon: Activity,
    sections: [],
    desc: "Engine health and system status",
  },
  {
    id: "models",
    label: "Models",
    icon: HardDrive,
    sections: [],
    desc: "Download and manage STT & TTS models",
  },
  {
    id: "general",
    label: "General",
    icon: Settings,
    sections: ["", "output"],
    desc: "Basic settings",
  },
  {
    id: "audio",
    label: "Audio",
    icon: Volume2,
    sections: ["audio"],
    desc: "Microphone, feedback sounds, and VAD sensitivity",
  },
  {
    id: "stt",
    label: "Transcription",
    icon: Mic,
    sections: ["stt"],
    desc: "Speech recognition model and language",
  },
  {
    id: "tts",
    label: "Voice",
    icon: AudioWaveform,
    sections: ["tts"],
    desc: "Text-to-speech engine and voice",
  },
  {
    id: "keyboard",
    label: "Keyboard",
    icon: Keyboard,
    sections: ["hotkey", "keyboard"],
    desc: "Hotkey and keyboard shortcuts",
  },
  {
    id: "agents",
    label: "Agents",
    icon: Bot,
    sections: ["agent_types"],
    desc: "Agent presets and default agent",
  },
  {
    id: "advanced",
    label: "Advanced",
    icon: SlidersHorizontal,
    sections: ["", "client", "logging", "stats", "daemon", "pipeline", "server"],
    desc: "Server, client, logging, daemon, and pipeline settings",
    children: [
      { id: "advanced-client", label: "Client", sections: ["client"], desc: "Agent client settings" },
      { id: "advanced-server", label: "Server", sections: ["server"], desc: "HTTP server host and port" },
      { id: "advanced-permissions", label: "Permissions", sections: [], desc: "Guided permission doctor" },
      { id: "advanced-pipeline", label: "Pipeline", sections: ["pipeline"], desc: "Message pipeline filters" },
    ],
  },
];

