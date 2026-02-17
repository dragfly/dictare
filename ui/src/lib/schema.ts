import type { JsonSchema, JsonSchemaProperty } from "./types";

export function resolveFieldSchema(
	key: string,
	schema: JsonSchema
): JsonSchemaProperty | null {
	const parts = key.split(".");

	if (parts.length === 1) {
		return schema.properties?.[parts[0]] ?? null;
	}

	const sectionProp = schema.properties?.[parts[0]];
	if (!sectionProp) return null;

	const ref = sectionProp.$ref || sectionProp.allOf?.[0]?.$ref;
	if (!ref) return null;

	const defName = ref.split("/").pop()!;
	const def = schema.$defs?.[defName];
	if (!def) return null;

	// 3-level key: e.g. pipeline.submit_filter.enabled
	if (parts.length === 3) {
		const subProp = def.properties?.[parts[1]];
		if (!subProp) return null;
		const subRef = subProp.$ref || subProp.allOf?.[0]?.$ref;
		if (!subRef) return null;
		const subDef = schema.$defs?.[subRef.split("/").pop()!];
		return subDef?.properties?.[parts[2]] ?? null;
	}

	return def.properties?.[parts.slice(1).join(".")] ?? null;
}

export function getEnumValues(
	fieldSchema: JsonSchemaProperty | null
): string[] | null {
	return fieldSchema?.enum ?? null;
}
