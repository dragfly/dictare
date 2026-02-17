<script lang="ts">
	import SettingsLayout from "$lib/components/settings/SettingsLayout.svelte";
	import {
		Volume2,
		Mic,
		AudioWaveform,
		Keyboard,
		MonitorSpeaker,
		Server,
		Settings,
		SlidersHorizontal
	} from "lucide-svelte";
	import type { TabDef } from "$lib/types";

	const tabs: TabDef[] = [
		{
			id: "general",
			label: "General",
			icon: Settings,
			sections: [""],
			desc: "General settings"
		},
		{
			id: "audio",
			label: "Audio",
			icon: Volume2,
			sections: ["audio"],
			desc: "Audio capture and feedback"
		},
		{
			id: "stt",
			label: "Speech",
			icon: Mic,
			sections: ["stt"],
			desc: "Whisper STT configuration"
		},
		{
			id: "tts",
			label: "Voice",
			icon: AudioWaveform,
			sections: ["tts"],
			desc: "Text-to-speech engine"
		},
		{
			id: "hotkey",
			label: "Hotkey",
			icon: Keyboard,
			sections: ["hotkey"],
			desc: "Toggle listening key"
		},
		{
			id: "output",
			label: "Output",
			icon: MonitorSpeaker,
			sections: ["output"],
			desc: "Text output mode and typing"
		},
		{
			id: "server",
			label: "Server",
			icon: Server,
			sections: ["server"],
			desc: "OpenVIP HTTP server"
		},
		{
			id: "advanced",
			label: "Advanced",
			icon: SlidersHorizontal,
			sections: ["client", "logging", "stats", "daemon", "pipeline"],
			desc: "Client, logging, daemon, and pipeline settings"
		}
	];
</script>

<svelte:head>
	<title>VoxType Settings</title>
</svelte:head>

<SettingsLayout {tabs} />
