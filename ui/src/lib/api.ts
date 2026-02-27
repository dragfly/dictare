import type { SchemaResponse } from "./types";

export async function fetchSchema(): Promise<SchemaResponse> {
	const r = await fetch("/settings/schema");
	if (!r.ok) throw new Error(`Failed to load schema: ${r.status}`);
	return r.json();
}

export async function saveSetting(
	key: string,
	value: unknown
): Promise<{ status: string; key: string; value: unknown }> {
	const r = await fetch("/settings", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ key, value: String(value) })
	});
	if (!r.ok) {
		const data = await r.json();
		throw new Error(data.detail || `Save failed: ${r.status}`);
	}
	return r.json();
}

export async function fetchTomlSection(section: string): Promise<string> {
	const r = await fetch(`/settings/toml-section/${section}`);
	if (!r.ok) throw new Error(`Failed to load section: ${r.status}`);
	const data = await r.json();
	return data.content as string;
}

export async function saveTomlSection(
	section: string,
	content: string
): Promise<void> {
	const r = await fetch(`/settings/toml-section/${section}`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ content })
	});
	if (!r.ok) {
		const data = await r.json().catch(() => ({}));
		throw new Error(data.detail || `Save failed: ${r.status}`);
	}
}

export type Shortcut = { keys: string; command: string };

export async function fetchShortcuts(): Promise<Shortcut[]> {
	const r = await fetch("/settings/shortcuts");
	if (!r.ok) throw new Error(`Failed to load shortcuts: ${r.status}`);
	const data = await r.json();
	return data.shortcuts as Shortcut[];
}

export async function saveShortcuts(shortcuts: Shortcut[]): Promise<void> {
	const r = await fetch("/settings/shortcuts", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ shortcuts }),
	});
	if (!r.ok) {
		const data = await r.json().catch(() => ({}));
		throw new Error(data.detail || `Save failed: ${r.status}`);
	}
}

export async function pingEngine(): Promise<boolean> {
	try {
		const r = await fetch("/control", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ command: "ping" })
		});
		return r.ok;
	} catch {
		return false;
	}
}

export async function captureHotkey(signal?: AbortSignal): Promise<string | null> {
	try {
		const r = await fetch("/control", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ command: "hotkey.capture", timeout: 10 }),
			signal,
		});
		if (!r.ok) return null;
		const data = await r.json();
		return data.key as string | null;
	} catch {
		return null;
	}
}

// ----- Audio Devices API -----

export type AudioDeviceInfo = {
	index: number;
	name: string;
	channels: number;
	sample_rate: number;
};

export type AudioDevicesResponse = {
	input: AudioDeviceInfo[];
	output: AudioDeviceInfo[];
	default_input: AudioDeviceInfo | null;
	default_output: AudioDeviceInfo | null;
};

export async function fetchAudioDevices(): Promise<AudioDevicesResponse> {
	const r = await fetch("/audio/devices");
	if (!r.ok) throw new Error(`Failed to load audio devices: ${r.status}`);
	return r.json();
}

// ----- Models API -----

export type ModelInfo = {
	id: string;
	type: "stt" | "tts";
	description: string;
	size_gb: number;
	cached: boolean;
	cache_size_bytes: number;
	configured: string;
	downloading: boolean;
	download_fraction: number | null;
	downloaded_bytes: number;
	total_bytes: number;
};

export async function fetchModels(): Promise<ModelInfo[]> {
	const r = await fetch("/models");
	if (!r.ok) throw new Error(`Failed to load models: ${r.status}`);
	const data = await r.json();
	return data.models as ModelInfo[];
}

export async function pullModel(modelId: string): Promise<string> {
	const r = await fetch(`/models/${modelId}/pull`, { method: "POST" });
	if (!r.ok) throw new Error(`Pull failed: ${r.status}`);
	const data = await r.json();
	return data.status as string;
}

export function createPullProgressSource(): EventSource {
	return new EventSource("/models/pull-progress");
}

// ----- Status / Dashboard API -----

export type EngineInfo = {
	name: string;
	available: boolean;
	description: string;
	platform_ok: boolean;
	install_hint: string;
	configured: boolean;
	venv_installed: boolean;
	needs_venv: boolean;
};

export type StatusResponse = {
	protocol_version: string;
	state: string;
	connected_agents: string[];
	platform: {
		name: string;
		version: string;
		mode: string;
		state: string;
		uptime_seconds: number;
		stt: { model_name: string; device: string; last_text: string };
		tts: { engine: string; language: string; available: boolean; error: string | null };
		output: { mode: string; current_agent: string; available_agents: string[] };
		hotkey: { key: string; bound: boolean };
		permissions: Record<string, boolean>;
		engines: {
			tts: EngineInfo[];
			stt: EngineInfo[];
		};
		loading: { active: boolean; models: { name: string; status: string }[] };
	};
};

export async function fetchStatus(): Promise<StatusResponse> {
	const r = await fetch("/status");
	if (!r.ok) throw new Error(`Failed to load status: ${r.status}`);
	return r.json();
}

export async function setCurrentAgent(agent: string): Promise<void> {
	try {
		await fetch("/control", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ command: `output.set_agent:${agent}` }),
		});
	} catch {
		// Engine might be briefly unresponsive
	}
}

export async function setOutputMode(mode: "keyboard" | "agents"): Promise<void> {
	try {
		await fetch("/control", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ command: `output.set_mode:${mode}` }),
		});
	} catch {
		// Engine might be briefly unresponsive
	}
}

export async function restartEngine(): Promise<void> {
	try {
		await fetch("/control", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ command: "engine.restart" })
		});
	} catch {
		// Expected: engine shuts down mid-restart, connection drops
	}
}

// ----- TTS Venv Install/Uninstall API -----

export async function installTtsEngine(engine: string): Promise<string> {
	const r = await fetch(`/tts-engines/${engine}/install`, { method: "POST" });
	if (!r.ok) throw new Error(`Install failed: ${r.status}`);
	const data = await r.json();
	return data.status as string;
}

export async function uninstallTtsEngine(engine: string): Promise<void> {
	const r = await fetch(`/tts-engines/${engine}/install`, { method: "DELETE" });
	if (!r.ok) throw new Error(`Uninstall failed: ${r.status}`);
}

// ----- Capabilities API (unified models + engines) -----

export type CapabilityInfo = {
	id: string;
	type: "stt" | "tts";
	description: string;
	size_gb: number;
	platform_ok: boolean;
	ready: boolean;
	venv_installed: boolean | null;
	model_cached: boolean | null;
	configured: boolean;
	builtin: boolean;
	downloading: boolean;
	download_fraction: number | null;
};

export async function fetchCapabilities(): Promise<CapabilityInfo[]> {
	const r = await fetch("/capabilities");
	if (!r.ok) throw new Error(`Failed to load capabilities: ${r.status}`);
	const data = await r.json();
	return data.capabilities as CapabilityInfo[];
}

export async function installCapability(id: string): Promise<string> {
	const r = await fetch(`/capabilities/${id}/install`, { method: "POST" });
	if (!r.ok) throw new Error(`Install failed: ${r.status}`);
	const data = await r.json();
	return data.status as string;
}

export async function uninstallCapability(id: string): Promise<void> {
	const r = await fetch(`/capabilities/${id}/install`, { method: "DELETE" });
	if (!r.ok) throw new Error(`Uninstall failed: ${r.status}`);
}

export async function selectCapability(id: string): Promise<void> {
	const r = await fetch(`/capabilities/${id}/select`, { method: "POST" });
	if (!r.ok) {
		const data = await r.json().catch(() => ({}));
		throw new Error(data.detail || `Select failed: ${r.status}`);
	}
}
