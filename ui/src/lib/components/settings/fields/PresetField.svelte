<script lang="ts">
	import * as Select from "$lib/components/ui/select";
	import { Input } from "$lib/components/ui/input";
	import { Button } from "$lib/components/ui/button";
	import { X } from "lucide-svelte";

	interface Props {
		options: string[];
		value: string;
		defaultValue?: string;
		onchange: (value: string) => void;
	}

	let { options, value, defaultValue, onchange }: Props = $props();

	let customMode = $state(false);
	let customValue = $state("");

	const SENTINEL = "__default__";
	const CUSTOM = "__custom__";

	const defaultLabel = $derived(
		defaultValue != null ? `Default (${defaultValue})` : "Default"
	);

	/** Check if current value is in the known options or is the default */
	const isKnown = $derived(
		value === defaultValue || value === "" || value == null || options.includes(value)
	);

	const displayValue = $derived(
		value === defaultValue || value === "" || value == null
			? SENTINEL
			: options.includes(value) ? value : CUSTOM
	);

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
		// Revert to default if custom value was empty
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
			{displayValue === SENTINEL ? defaultLabel : value}
		</Select.Trigger>
		<Select.Content>
			<Select.Item value={SENTINEL} label={defaultLabel} />
			{#each options as opt (opt)}
				{#if opt !== defaultValue}
					<Select.Item value={opt} label={opt} />
				{/if}
			{/each}
			<Select.Item value={CUSTOM} label="Custom…" />
		</Select.Content>
	</Select.Root>
{/if}
