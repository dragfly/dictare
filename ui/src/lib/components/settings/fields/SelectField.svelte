<script lang="ts">
	import * as Select from "$lib/components/ui/select";
	import { Input } from "$lib/components/ui/input";
	import { Button } from "$lib/components/ui/button";
	import { X } from "lucide-svelte";

	interface Props {
		/** The normalized option list — already {value, label} pairs. */
		options: { value: string; label: string }[];
		/** Current value. "" means "use default" (dirty sentinel). */
		value: string;
		/** Display string for the default, e.g. "agents" or "Built-in Microphone". */
		defaultDisplay: string;
		/** If true, show a "Custom…" entry and allow free-text input. */
		allowCustom?: boolean;
		onchange: (value: string) => void;
	}

	let { options, value, defaultDisplay, allowCustom = false, onchange }: Props = $props();

	/** Internal sentinel for the Select widget — never emitted externally. */
	const SENTINEL = "__default__";
	const CUSTOM = "__custom__";

	let customMode = $state(false);
	let customValue = $state("");

	const optionValues = $derived(options.map((o) => o.value));

	const defaultLabel = $derived(defaultDisplay ? `Default (${defaultDisplay})` : "Default");

	const isDefault = $derived(value === "" || value == null);
	const isKnown = $derived(isDefault || optionValues.includes(value));

	const displayValue = $derived(
		isDefault ? SENTINEL : isKnown ? value : CUSTOM
	);

	const displayLabel = $derived.by(() => {
		if (displayValue === SENTINEL) return defaultLabel;
		if (displayValue === CUSTOM) return value;
		const opt = options.find((o) => o.value === value);
		return opt ? opt.label : value;
	});

	// If current value isn't in options, enter custom mode automatically
	$effect(() => {
		if (allowCustom && !isKnown && value && value !== "") {
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
		// "" = sentinel for "use default" — backend deletes TOML key
		onchange(v === SENTINEL ? "" : v);
	}

	function handleCustomSubmit() {
		if (customValue.trim()) {
			onchange(customValue.trim());
		}
	}

	function exitCustomMode() {
		customMode = false;
		if (!customValue.trim()) {
			onchange("");
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
		<Select.Trigger class="w-fit max-w-64 whitespace-nowrap">
			<span class="truncate">{displayLabel}</span>
		</Select.Trigger>
		<Select.Content>
			<Select.Item value={SENTINEL} label={defaultLabel} />
			{#each options as opt (opt.value)}
				<Select.Item value={opt.value} label={opt.label} />
			{/each}
			{#if allowCustom}
				<Select.Item value={CUSTOM} label="Custom…" />
			{/if}
		</Select.Content>
	</Select.Root>
{/if}
