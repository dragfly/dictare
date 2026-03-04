import { fetchSchema, saveSetting, saveTomlSection, selectCapability, restartEngine } from "$lib/api";
import type { SchemaResponse } from "$lib/types";

let schema = $state<SchemaResponse | null>(null);
let dirty = $state<Record<string, unknown>>({});
let dirtyToml = $state<Record<string, string>>({});
let dirtyModels = $state<Record<string, string>>({});
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
	return engineBarVisible ? 44 : 0;
}
export function hasDirtyFields(): boolean {
	return (
		Object.keys(dirty).length > 0 ||
		Object.keys(dirtyToml).length > 0 ||
		Object.keys(dirtyModels).length > 0
	);
}

// --- TOML dirty tracking ---
export function markTomlDirty(section: string, content: string): void {
	dirtyToml = { ...dirtyToml, [section]: content };
	saveStatus = "idle";
}
export function markTomlClean(section: string): void {
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

export function resetDirty(): void {
	dirty = {};
	dirtyToml = {};
	dirtyModels = {};
	saveErrors = {};
	saveStatus = "idle";
}

export function clearSaveStatus(): void {
	if (saveStatus === "saved") {
		saveStatus = "idle";
	}
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

	if (errorCount === 0) {
		dirty = {};
		dirtyToml = {};
		dirtyModels = {};
		saveStatus = "saved";
		// Auto-restart engine after successful save
		await restartEngine();
		schema = await fetchSchema();
	} else {
		saveErrors = errors;
		saveStatus = "error";
	}
}
