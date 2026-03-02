import { fetchPresets, type PresetsResponse } from "$lib/api";

let data = $state<PresetsResponse>({});

export async function load(): Promise<void> {
	try {
		data = await fetchPresets();
	} catch {
		// Non-fatal — UI falls back gracefully (shows "Default" without the value)
	}
}

export function getDefault(key: string): string {
	const entry = data[key];
	if (!entry) return "";
	const d = entry.default;
	return d == null ? "" : String(d);
}

export function getValues(key: string): { value: string; label: string }[] | undefined {
	return data[key]?.values;
}
