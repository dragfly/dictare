<script lang="ts">
	import type { FieldMeta, JsonSchema } from "$lib/types";
	import BoolField from "./fields/BoolField.svelte";
	import StringField from "./fields/StringField.svelte";
	import NumberField from "./fields/NumberField.svelte";
	import EnumField from "./fields/EnumField.svelte";
	import PresetField from "./fields/PresetField.svelte";
	import ComplexField from "./fields/ComplexField.svelte";
	import TomlField from "./fields/TomlField.svelte";
	import ShortcutsField from "./fields/ShortcutsField.svelte";
	import KeyCaptureField from "./fields/KeyCaptureField.svelte";
	import DeviceField from "./fields/DeviceField.svelte";
	import { resolveFieldSchema, getEnumValues } from "$lib/schema";
	import * as settingsStore from "$lib/stores/settings.svelte";
	import { COMPLEX_KEYS, TOML_EDITABLE_KEYS, TOML_NO_ACCORDION, FIELD_PRESETS, SIZE_HINTS, HIDDEN_FORM_FIELDS, KEY_CAPTURE_FIELDS, RIGHT_ALIGN_FIELDS, LABEL_OVERRIDES, DEVICE_FIELDS } from "$lib/registry/field-config";

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
	const isHiddenByParentToml = $derived(
		(() => {
			const parts = field.key.split(".");
			for (let i = 1; i < parts.length; i++) {
				if (TOML_EDITABLE_KEYS.has(parts.slice(0, i).join("."))) return true;
			}
			return false;
		})()
	);
	const keyCaptureFormat = $derived(KEY_CAPTURE_FIELDS[field.key] as "evdev" | "shortcut" | undefined);
	const deviceDirection = $derived(DEVICE_FIELDS[field.key] as "input" | "output" | undefined);
	const presets = $derived(FIELD_PRESETS[field.key]);
	const currentValue = $derived(settingsStore.getValue(field.key));
	const isDirty = $derived(field.key in settingsStore.getDirty());
	const error = $derived(settingsStore.getSaveErrors()[field.key]);
	const label = $derived(LABEL_OVERRIDES[field.key] ?? humanize(field.key));
	const size = $derived((SIZE_HINTS[field.key] ?? "normal") as "narrow" | "medium" | "normal");
	const align = $derived(RIGHT_ALIGN_FIELDS.has(field.key) ? "right" as const : "left" as const);

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

{#if HIDDEN_FORM_FIELDS.has(field.key) || isHiddenByParentToml}
	<!-- hidden: excluded from UI or child of a TOML-editable section -->
{:else if field.key === "keyboard.shortcuts"}
	<!-- Structured shortcuts editor -->
	<div class="px-4">
		<ShortcutsField />
	</div>
{:else if isTomlEditable}
	<!-- Full-width TOML editor — no inline label/control split -->
	<div class="px-4">
		<TomlField section={field.key} label={label} noAccordion={TOML_NO_ACCORDION.has(field.key)} />
	</div>
{:else}
<div
	class="flex items-start justify-between gap-6 rounded-lg px-4 py-3 transition-colors hover:bg-accent/30
		{isDirty ? 'bg-accent/20 border-l-2 border-primary' : ''}"
>
	<!-- Left: label + description -->
	<div class="flex flex-col gap-0.5 min-w-0">
		<div class="flex items-center gap-1.5">
			<span class="text-sm font-medium {isNonDefault ? 'text-amber-500 dark:text-amber-400' : ''}">{label}</span>
			{#if isNonDefault}
				<span class="size-1.5 rounded-full bg-amber-500 dark:bg-amber-400 shrink-0"></span>
			{/if}
		</div>
		{#if field.description}
			<p class="text-xs text-muted-foreground leading-relaxed">{field.description}</p>
		{/if}
	</div>

	<!-- Right: control -->
	<div class="flex items-center gap-2 shrink-0 mt-0.5">
		{#if deviceDirection}
			<DeviceField
				direction={deviceDirection}
				value={(currentValue as string) ?? ""}
				onchange={(v) => settingsStore.markDirty(field.key, v)}
			/>
		{:else if keyCaptureFormat}
			<KeyCaptureField
				format={keyCaptureFormat}
				value={(currentValue as string) ?? ""}
				onchange={(v) => settingsStore.markDirty(field.key, v)}
			/>
		{:else if complex}
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
				{align}
				onchange={(v) => settingsStore.markDirty(field.key, v)}
			/>
		{/if}
	</div>
</div>

{#if error}
	<p class="text-xs text-destructive px-4 -mt-1 mb-1">{error}</p>
{/if}
{/if}
