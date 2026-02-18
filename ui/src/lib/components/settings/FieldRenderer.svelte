<script lang="ts">
	import type { FieldMeta, JsonSchema } from "$lib/types";
	import BoolField from "./fields/BoolField.svelte";
	import StringField from "./fields/StringField.svelte";
	import NumberField from "./fields/NumberField.svelte";
	import EnumField from "./fields/EnumField.svelte";
	import PresetField from "./fields/PresetField.svelte";
	import ComplexField from "./fields/ComplexField.svelte";
	import TomlField from "./fields/TomlField.svelte";
	import { resolveFieldSchema, getEnumValues } from "$lib/schema";
	import * as settingsStore from "$lib/stores/settings.svelte";
	import * as Tooltip from "$lib/components/ui/tooltip";
	import { Info } from "lucide-svelte";
	import { COMPLEX_KEYS, TOML_EDITABLE_KEYS, FIELD_PRESETS, SIZE_HINTS } from "$lib/generated/field-config";

	interface Props {
		field: FieldMeta;
		schema: JsonSchema;
	}

	let { field, schema }: Props = $props();

	function isComplex(f: FieldMeta): boolean {
		for (const ck of COMPLEX_KEYS) {
			if (f.key === ck || f.key.startsWith(ck + ".")) return true;
		}
		return f.type === "dict" || f.type === "list";
	}

	/** Known acronyms that should stay uppercase */
	const ACRONYMS = new Set(["tts", "stt", "url", "wpm", "vad", "api", "sse", "pid", "hw", "ms"]);

	/** Derive a short human label from the dotted key */
	function humanize(key: string): string {
		const last = key.split(".").pop() ?? key;
		return last
			.split("_")
			.map((w) => ACRONYMS.has(w) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1))
			.join(" ");
	}

	const fieldSchema = $derived(resolveFieldSchema(field.key, schema));
	const enumValues = $derived(getEnumValues(fieldSchema));
	const complex = $derived(isComplex(field));
	const isTomlEditable = $derived(TOML_EDITABLE_KEYS.has(field.key));
	const presets = $derived(FIELD_PRESETS[field.key]);
	const currentValue = $derived(settingsStore.getValue(field.key));
	const isDirty = $derived(field.key in settingsStore.getDirty());
	const error = $derived(settingsStore.getSaveErrors()[field.key]);
	const label = $derived(humanize(field.key));
	const size = $derived((SIZE_HINTS[field.key] ?? "normal") as "narrow" | "medium" | "normal");

	/** True when the saved config value differs from the schema default. */
	const isNonDefault = $derived(
		!isDirty &&
		field.default !== null &&
		field.default !== undefined &&
		JSON.stringify(currentValue) !== JSON.stringify(field.default)
	);

	/** Placeholder text for empty string fields — shows the default value. */
	const placeholder = $derived(
		field.type === "str" && typeof field.default === "string" && field.default !== ""
			? field.default
			: ""
	);
</script>

{#if isTomlEditable}
	<!-- Full-width TOML editor — no inline label/control split -->
	<div class="px-4">
		<TomlField section={field.key} label={label} />
	</div>
{:else}
<div
	class="flex items-center justify-between gap-4 rounded-lg px-4 py-3 transition-colors hover:bg-accent/30
		{isDirty ? 'bg-accent/20 border-l-2 border-primary' : ''}"
>
	<!-- Left: label + info tooltip -->
	<div class="flex items-center gap-1.5 min-w-0 shrink-0">
		<span class="text-sm font-medium whitespace-nowrap {isNonDefault ? 'text-amber-500 dark:text-amber-400' : ''}">{label}</span>
		{#if isNonDefault}
			<span class="size-1.5 rounded-full bg-amber-500 dark:bg-amber-400 shrink-0" title="Custom value (differs from default)"></span>
		{/if}
		<Tooltip.Root>
			<Tooltip.Trigger class="text-muted-foreground hover:text-foreground transition-colors">
				<Info class="size-3.5" />
			</Tooltip.Trigger>
			<Tooltip.Content side="right" class="max-w-sm space-y-1.5 text-xs break-words">
				{#if field.description}
					<p>{field.description}</p>
				{/if}
				<p class="font-mono text-muted-foreground">
					{field.key}
				</p>
				{#if field.env_var}
					<p class="font-mono text-muted-foreground">
						{field.env_var}
					</p>
				{/if}
				{#if field.default !== null && field.default !== undefined}
					<p class="text-muted-foreground">
						Default: <code class="font-mono">{JSON.stringify(field.default)}</code>
					</p>
				{/if}
			</Tooltip.Content>
		</Tooltip.Root>
	</div>

	<!-- Right: control -->
	<div class="flex items-center gap-2 shrink-0">
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
				defaultValue={field.default as string}
				onchange={(v) => settingsStore.markDirty(field.key, v)}
			/>
		{:else if presets}
			<PresetField
				options={presets}
				value={(currentValue as string) ?? ""}
				defaultValue={field.default as string}
				onchange={(v) => settingsStore.markDirty(field.key, v)}
			/>
		{:else if field.type === "int" || field.type === "float"}
			<NumberField
				value={currentValue as number}
				step={field.type === "float" ? 0.01 : 1}
				{size}
				onchange={(v) => settingsStore.markDirty(field.key, v)}
			/>
		{:else}
			<StringField
				value={(currentValue as string) ?? ""}
				{placeholder}
				{size}
				onchange={(v) => settingsStore.markDirty(field.key, v)}
			/>
		{/if}
	</div>
</div>

{#if error}
	<p class="text-xs text-destructive px-4 -mt-1 mb-1">{error}</p>
{/if}
{/if}
