import { fetchSchema, saveSetting, saveTomlSection, saveShortcuts, selectCapability, restartEngine, type Shortcut, type StatusResponse } from "$lib/api";
import type { SchemaResponse } from "$lib/types";

let schema = $state<SchemaResponse | null>(null);
let dirty = $state<Record<string, unknown>>({});
let dirtyToml = $state<Record<string, string>>({});
let dirtyModels = $state<Record<string, string>>({});
let dirtyShortcuts = $state<Shortcut[] | null>(null);
let saveStatus = $state<"idle" | "saving" | "saved" | "error">("idle");
let saveErrors = $state<Record<string, string>>({});
let engineBarVisible = $state(false);

export function getSchema(): SchemaResponse | null {
	return schema;
}
export function getDirty(): Record<string, unknown> {
	return dirty;
}
export function getDirtyToml(): Record<string, string> {
	return dirtyToml;
}
export function getDirtyModels(): Record<string, string> {
	return dirtyModels;
}
export function getSaveStatus(): string {
	return saveStatus;
}
export function setSaveStatus(s: "idle" | "saving" | "saved" | "error"): void {
	saveStatus = s;
}
export function getSaveErrors(): Record<string, string> {
	return saveErrors;
}
export function getEngineBarVisible(): boolean {
	return engineBarVisible;
}
export function setEngineBarVisible(v: boolean): void {
	engineBarVisible = v;
}
/** Total px that fixed bottom bars occupy — use as padding-bottom on the scroll container. */
export function getFixedBottomPx(): number {
	const saveBar = hasDirtyFields() || saveStatus === "error" ? 52 : 0;
	return (engineBarVisible ? 44 : 0) + saveBar;
}
export function hasDirtyFields(): boolean {
	return (
		Object.keys(dirty).length > 0 ||
		Object.keys(dirtyToml).length > 0 ||
		Object.keys(dirtyModels).length > 0 ||
		dirtyShortcuts !== null
	);
}

// --- TOML section getters ---
/** Return the current content for a TOML section (dirty if edited, else from schema). */
export function getTomlSection(section: string): string {
	if (section in dirtyToml) return dirtyToml[section];
	return schema?.toml_sections[section] ?? "";
}

export function markTomlDirty(section: string, content: string): void {
	dirtyToml = { ...dirtyToml, [section]: content };
	saveStatus = "idle";
}
export function markTomlClean(section: string): void {
	if (!(section in dirtyToml)) return;
	const { [section]: _, ...rest } = dirtyToml;
	dirtyToml = rest;
}

// --- Model dirty tracking ---
export function markModelDirty(type: string, id: string): void {
	dirtyModels = { ...dirtyModels, [type]: id };
	saveStatus = "idle";
}
export function clearModelDirty(type: string): void {
	const { [type]: _, ...rest } = dirtyModels;
	dirtyModels = rest;
}

// --- Shortcuts getters ---
/** Return the current shortcuts (dirty if edited, else from schema). */
export function getShortcuts(): Shortcut[] {
	if (dirtyShortcuts !== null) return dirtyShortcuts;
	return schema?.shortcuts ?? [];
}
export function markShortcutsDirty(rows: Shortcut[]): void {
	dirtyShortcuts = rows;
	saveStatus = "idle";
}

// --- Presets getters ---
export function getPresetDefault(key: string): string {
	const entry = schema?.presets[key];
	if (!entry) return "";
	const d = entry.default;
	return d == null ? "" : String(d);
}
export function getPresetValues(key: string): { value: string; label: string }[] | undefined {
	return schema?.presets[key]?.values;
}

export function resetDirty(): void {
	dirty = {};
	dirtyToml = {};
	dirtyModels = {};
	dirtyShortcuts = null;
	saveErrors = {};
	saveStatus = "idle";
}

export async function load(): Promise<void> {
	schema = await fetchSchema();
}

export function getValue(key: string): unknown {
	if (key in dirty) return dirty[key];
	if (!schema) return null;
	const parts = key.split(".");
	let obj: Record<string, unknown> = schema.values;
	for (const p of parts) {
		if (obj == null) return null;
		obj = obj[p] as Record<string, unknown>;
	}
	return obj;
}

export function markDirty(key: string, value: unknown): void {
	dirty = { ...dirty, [key]: value };
	saveStatus = "idle";
	const { [key]: _, ...rest } = saveErrors;
	saveErrors = rest;
}

export function updateDeviceLists(status: StatusResponse): void {
	const devices = status.platform?.audio_devices_available;
	if (!devices || !schema) return;

	if (schema.presets["audio.input_device"]) {
		schema.presets["audio.input_device"] = {
			...schema.presets["audio.input_device"],
			values: devices.input.map((d) => ({ value: d.name, label: d.name })),
			default: devices.default_input?.name ?? "",
		};
	}
	if (schema.presets["audio.output_device"]) {
		schema.presets["audio.output_device"] = {
			...schema.presets["audio.output_device"],
			values: devices.output.map((d) => ({ value: d.name, label: d.name })),
			default: devices.default_output?.name ?? "",
		};
	}
	// Force reactivity
	schema = { ...schema };
}

export async function saveAll(): Promise<void> {
	saveStatus = "saving";
	const errors: Record<string, string> = {};
	let errorCount = 0;

	// Save form fields
	for (const [key, value] of Object.entries(dirty)) {
		try {
			await saveSetting(key, value);
		} catch (e) {
			errors[key] = (e as Error).message;
			errorCount++;
		}
	}

	// Save TOML sections
	for (const [section, content] of Object.entries(dirtyToml)) {
		try {
			await saveTomlSection(section, content);
		} catch (e) {
			errors[`toml:${section}`] = (e as Error).message;
			errorCount++;
		}
	}

	// Save model selections
	for (const [, id] of Object.entries(dirtyModels)) {
		try {
			await selectCapability(id);
		} catch (e) {
			errors[`model:${id}`] = (e as Error).message;
			errorCount++;
		}
	}

	// Save shortcuts
	if (dirtyShortcuts !== null) {
		const valid = dirtyShortcuts.filter((r) => r.keys && r.command);
		try {
			await saveShortcuts(valid);
		} catch (e) {
			errors["shortcuts"] = (e as Error).message;
			errorCount++;
		}
	}

	if (errorCount === 0) {
		// Apply saved values into the in-memory schema so the UI doesn't
		// flicker back to pre-save values while the engine restarts.
		if (schema) {
			for (const [key, value] of Object.entries(dirty)) {
				const parts = key.split(".");
				let obj: Record<string, unknown> = schema.values;
				for (const p of parts.slice(0, -1)) {
					if (obj[p] == null) break;
					obj = obj[p] as Record<string, unknown>;
				}
				obj[parts[parts.length - 1]] = value;
			}
			for (const [section, content] of Object.entries(dirtyToml)) {
				schema.toml_sections[section] = content;
			}
			if (dirtyShortcuts !== null) {
				schema.shortcuts = dirtyShortcuts.filter((r) => r.keys && r.command);
			}
			// Force reactivity by reassigning
			schema = { ...schema };
		}
		dirty = {};
		dirtyToml = {};
		dirtyModels = {};
		dirtyShortcuts = null;
		saveStatus = "saved";
		// Auto-restart engine — EngineStatusBar will poll and call load()
		// when the engine is back up, which reloads the full schema.
		await restartEngine();
	} else {
		saveErrors = errors;
		saveStatus = "error";
	}
}
