<script lang="ts">
	import * as Select from "$lib/components/ui/select";
	import { Input } from "$lib/components/ui/input";
	import { Button } from "$lib/components/ui/button";
	import { X } from "lucide-svelte";
	import type { PresetOption } from "$lib/registry/field-config";

	interface Props {
		options: PresetOption[];
		value: string;
		defaultValue?: string;
		onchange: (value: string) => void;
	}

	let { options, value, defaultValue, onchange }: Props = $props();

	let customMode = $state(false);
	let customValue = $state("");

	const SENTINEL = "__default__";
	const CUSTOM = "__custom__";

	/** Extract the raw value from a preset option */
	function optValue(opt: PresetOption): string {
		return typeof opt === "string" ? opt : opt.value;
	}

	/** Extract the display label from a preset option */
	function optLabel(opt: PresetOption): string {
		return typeof opt === "string" ? opt : opt.label;
	}

	const allValues = $derived(options.map(optValue));

	const defaultLabel = $derived(
		defaultValue != null ? `Default (${defaultValue})` : "Default"
	);

	/** Check if current value is in the known options or is the default */
	const isKnown = $derived(
		value === defaultValue || value === "" || value == null || allValues.includes(value)
	);

	const displayValue = $derived(
		value === defaultValue || value === "" || value == null
			? SENTINEL
			: allValues.includes(value) ? value : CUSTOM
	);

	/** Find the label for the current value */
	const currentLabel = $derived(() => {
		if (displayValue === SENTINEL) return defaultLabel;
		const opt = options.find((o) => optValue(o) === value);
		return opt ? optLabel(opt) : value;
	});

	// If current value isn't in presets, start in custom mode
	$effect(() => {
		if (!isKnown && value) {
			customMode = true;
			customValue = value;
		}
	});

	function handleSelect(v: string) {
		if (v === CUSTOM) {
			customMode = true;
			customValue = value || "";
			return;
		}
		customMode = false;
		if (v === SENTINEL) {
			onchange(defaultValue ?? "");
		} else {
			onchange(v);
		}
	}

	function handleCustomSubmit() {
		if (customValue.trim()) {
			onchange(customValue.trim());
		}
	}

	function exitCustomMode() {
		customMode = false;
		if (!customValue.trim()) {
			onchange(defaultValue ?? "");
		}
	}
</script>

{#if customMode}
	<div class="flex items-center gap-1">
		<Input
			type="text"
			class="w-36"
			value={customValue}
			oninput={(e) => { customValue = e.currentTarget.value; }}
			onchange={handleCustomSubmit}
			placeholder="Custom value…"
		/>
		<Button variant="ghost" size="icon" class="size-8 shrink-0" onclick={exitCustomMode}>
			<X class="size-3.5" />
		</Button>
	</div>
{:else}
	<Select.Root type="single" value={displayValue} onValueChange={(v) => { if (v) handleSelect(v); }}>
		<Select.Trigger class="w-48">
			{currentLabel()}
		</Select.Trigger>
		<Select.Content>
			<Select.Item value={SENTINEL} label={defaultLabel} />
			{#each options as opt (optValue(opt))}
				<Select.Item value={optValue(opt)} label={optLabel(opt)} />
			{/each}
			<Select.Item value={CUSTOM} label="Custom…" />
		</Select.Content>
	</Select.Root>
{/if}
