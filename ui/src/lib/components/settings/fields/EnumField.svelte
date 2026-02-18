<script lang="ts">
	import * as Select from "$lib/components/ui/select";

	interface Props {
		options: string[];
		value: string;
		defaultValue?: string;
		onchange: (value: string) => void;
	}

	let { options, value, defaultValue, onchange }: Props = $props();

	/** Capitalize first letter of each word */
	function capitalize(s: string): string {
		return s.replace(/\b\w/g, (c) => c.toUpperCase());
	}

	const defaultLabel = $derived(
		defaultValue != null ? `Default (${defaultValue})` : "Default"
	);

	/** Internal value: use sentinel to represent "use default" */
	const SENTINEL = "__default__";

	const displayValue = $derived(
		value === defaultValue || value === "" || value == null ? SENTINEL : value
	);

	function handleChange(v: string) {
		if (v === SENTINEL) {
			onchange(defaultValue ?? "");
		} else {
			onchange(v);
		}
	}

	const displayLabel = $derived(
		displayValue === SENTINEL
			? defaultLabel
			: capitalize(value)
	);
</script>

<Select.Root type="single" value={displayValue} onValueChange={(v) => { if (v) handleChange(v); }}>
	<Select.Trigger class="w-fit whitespace-nowrap">
		{displayLabel}
	</Select.Trigger>
	<Select.Content>
		<Select.Item value={SENTINEL} label={defaultLabel} />
		{#each options as opt (opt)}
			<Select.Item value={opt} label={capitalize(opt)} />
		{/each}
	</Select.Content>
</Select.Root>
