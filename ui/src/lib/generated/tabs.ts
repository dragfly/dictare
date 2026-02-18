import {
  AudioWaveform,
  Bot,
  Keyboard,
  Mic,
  MonitorSpeaker,
  Server,
  Settings,
  SlidersHorizontal,
  Volume2,
} from "lucide-svelte";
import type { TabDef } from "$lib/types";

export const tabs: TabDef[] = [
  {
    id: "general",
    label: "General",
    icon: Settings,
    sections: [""],
    desc: "General settings",
  },
  {
    id: "audio",
    label: "Audio",
    icon: Volume2,
    sections: ["audio"],
    desc: "Audio capture and feedback",
  },
  {
    id: "stt",
    label: "Speech",
    icon: Mic,
    sections: ["stt"],
    desc: "Whisper STT configuration",
  },
  {
    id: "tts",
    label: "Voice",
    icon: AudioWaveform,
    sections: ["tts"],
    desc: "Text-to-speech engine",
  },
  {
    id: "keyboard",
    label: "Keyboard",
    icon: Keyboard,
    sections: ["hotkey", "keyboard"],
    desc: "Hotkey and shortcuts",
    children: [
      {
        id: "keyboard-hotkey",
        label: "Hotkey",
        sections: ["hotkey"],
        desc: "Toggle listening key",
      },
      {
        id: "keyboard-shortcuts",
        label: "Shortcuts",
        sections: ["keyboard"],
        desc: "Keyboard shortcuts",
      },
    ],
  },
  {
    id: "output",
    label: "Output",
    icon: MonitorSpeaker,
    sections: ["output"],
    desc: "Text output mode and typing",
  },
  {
    id: "agents",
    label: "Agents",
    icon: Bot,
    sections: ["agent_types"],
    desc: "Agent type presets and default agent",
  },
  {
    id: "server",
    label: "Server",
    icon: Server,
    sections: ["server"],
    desc: "OpenVIP HTTP server",
  },
  {
    id: "advanced",
    label: "Advanced",
    icon: SlidersHorizontal,
    sections: ["client", "logging", "stats", "daemon", "pipeline"],
    desc: "Client, logging, daemon, and pipeline settings",
    children: [
      { id: "advanced-client",   label: "Client",     sections: ["client"],   desc: "Agent client settings" },
      { id: "advanced-logging",  label: "Logging",    sections: ["logging"],  desc: "Log file and level" },
      { id: "advanced-stats",    label: "Statistics", sections: ["stats"],    desc: "Typing statistics" },
      { id: "advanced-daemon",   label: "Daemon",     sections: ["daemon"],   desc: "Background service" },
      { id: "advanced-pipeline", label: "Pipeline",   sections: ["pipeline"], desc: "Message pipeline filters" },
    ],
  },
];
