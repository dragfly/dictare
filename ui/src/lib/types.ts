import type { Component } from "svelte";

export interface FieldMeta {
	key: string;
	type: string;
	default: unknown;
	description: string;
	env_var: string;
}

export interface PresetEntry {
	default: unknown;
	values?: { value: string; label: string }[];
}

export interface SchemaResponse {
	schema: JsonSchema;
	values: Record<string, unknown>;
	keys: FieldMeta[];
	version: string;
	toml_sections: Record<string, string>;
	shortcuts: { keys: string; command: string }[];
	presets: Record<string, PresetEntry>;
}

export interface JsonSchema {
	properties?: Record<string, JsonSchemaProperty>;
	$defs?: Record<string, JsonSchemaDefinition>;
}

export interface JsonSchemaProperty {
	type?: string;
	enum?: string[];
	$ref?: string;
	allOf?: Array<{ $ref?: string }>;
	description?: string;
	default?: unknown;
}

export interface JsonSchemaDefinition {
	properties?: Record<string, JsonSchemaProperty>;
}

/** A leaf nav item — shows only its own sections in the content area. */
export interface NavChild {
	id: string;
	label: string;
	sections: string[];
	desc: string;
}

export interface TabDef {
	id: string;
	label: string;
	icon: Component;
	sections: string[];
	desc: string;
	/** If present, this tab is expandable in the nav and shows children instead of flat content. */
	children?: NavChild[];
}
