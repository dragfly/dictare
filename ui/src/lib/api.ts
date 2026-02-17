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

export async function restartEngine(): Promise<void> {
	try {
		await fetch("/control", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ command: "engine.shutdown" })
		});
	} catch {
		// Expected: engine shuts down, connection drops
	}
}
