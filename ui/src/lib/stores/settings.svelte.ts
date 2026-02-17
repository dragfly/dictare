import { fetchSchema, saveSetting } from "$lib/api";
import type { SchemaResponse } from "$lib/types";

let schema = $state<SchemaResponse | null>(null);
let dirty = $state<Record<string, unknown>>({});
let saveStatus = $state<"idle" | "saving" | "saved" | "error">("idle");
let saveErrors = $state<Record<string, string>>({});
let needsRestart = $state(false);

export function getSchema(): SchemaResponse | null {
	return schema;
}
export function getDirty(): Record<string, unknown> {
	return dirty;
}
export function getSaveStatus(): string {
	return saveStatus;
}
export function getSaveErrors(): Record<string, string> {
	return saveErrors;
}
export function getNeedsRestart(): boolean {
	return needsRestart;
}
export function hasDirtyFields(): boolean {
	return Object.keys(dirty).length > 0;
}

export function resetDirty(): void {
	dirty = {};
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

	for (const [key, value] of Object.entries(dirty)) {
		try {
			await saveSetting(key, value);
		} catch (e) {
			errors[key] = (e as Error).message;
			errorCount++;
		}
	}

	if (errorCount === 0) {
		dirty = {};
		saveStatus = "saved";
		needsRestart = true;
		schema = await fetchSchema();
	} else {
		saveErrors = errors;
		saveStatus = "error";
	}
}
