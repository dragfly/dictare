<script lang="ts">
	import type { FieldMeta, JsonSchema } from "$lib/types";
	import BoolField from "./fields/BoolField.svelte";
	import StringField from "./fields/StringField.svelte";
	import NumberField from "./fields/NumberField.svelte";
	import EnumField from "./fields/EnumField.svelte";
	import ComplexField from "./fields/ComplexField.svelte";
	import { resolveFieldSchema, getEnumValues } from "$lib/schema";
	import * as settingsStore from "$lib/stores/settings.svelte";

	interface Props {
		field: FieldMeta;
		schema: JsonSchema;
	}

	let { field, schema }: Props = $props();

	const COMPLEX_KEYS = new Set([
		"audio.sounds",
		"keyboard.shortcuts",
		"pipeline.submit_filter.triggers",
		"agents"
	]);

	function isComplex(f: FieldMeta): boolean {
		for (const ck of COMPLEX_KEYS) {
			if (f.key === ck || f.key.startsWith(ck + ".")) return true;
		}
		return f.type === "dict" || f.type === "list";
	}

	const fieldSchema = $derived(resolveFieldSchema(field.key, schema));
	const enumValues = $derived(getEnumValues(fieldSchema));
	const complex = $derived(isComplex(field));
	const currentValue = $derived(settingsStore.getValue(field.key));
	const isDirty = $derived(field.key in settingsStore.getDirty());
	const error = $derived(settingsStore.getSaveErrors()[field.key]);
</script>

<div
	class="group rounded-lg px-4 py-3 transition-colors hover:bg-accent/30
		{isDirty ? 'bg-accent/20 border-l-2 border-primary' : ''}"
>
	<div class="flex items-baseline gap-2 mb-1">
		<span class="text-sm font-medium">{field.description || field.key}</span>
		<code class="text-[11px] text-muted-foreground font-mono">{field.key}</code>
	</div>

	{#if complex}
		<ComplexField />
	{:else if field.type === "bool"}
		<BoolField
			checked={currentValue as boolean}
			onchange={(v) => settingsStore.markDirty(field.key, v)}
		/>
	{:else if enumValues}
		<EnumField
			options={enumValues}
			value={currentValue as string}
			onchange={(v) => settingsStore.markDirty(field.key, v)}
		/>
	{:else if field.type === "int" || field.type === "float"}
		<NumberField
			value={currentValue as number}
			step={field.type === "float" ? 0.01 : 1}
			onchange={(v) => settingsStore.markDirty(field.key, v)}
		/>
	{:else}
		<StringField
			value={(currentValue as string) ?? ""}
			onchange={(v) => settingsStore.markDirty(field.key, v)}
		/>
	{/if}

	{#if field.default !== null && field.default !== undefined && !complex}
		<p class="text-[11px] text-muted-foreground mt-1.5">
			Default: <code class="font-mono">{JSON.stringify(field.default)}</code>
		</p>
	{/if}
	{#if field.env_var}
		<p class="text-[10px] text-muted-foreground/60 font-mono mt-0.5">{field.env_var}</p>
	{/if}
	{#if error}
		<p class="text-xs text-destructive mt-1">{error}</p>
	{/if}
</div>
