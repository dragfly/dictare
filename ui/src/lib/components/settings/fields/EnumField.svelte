<script lang="ts">
	import * as Select from "$lib/components/ui/select";

	interface Props {
		options: string[];
		value: string;
		onchange: (value: string) => void;
	}

	let { options, value, onchange }: Props = $props();
</script>

<Select.Root type="single" {value} onValueChange={(v) => { if (v) onchange(v); }}>
	<Select.Trigger class="w-auto min-w-[10rem]">
		{value || "Select..."}
	</Select.Trigger>
	<Select.Content>
		{#each options as opt (opt)}
			<Select.Item value={opt} label={opt} />
		{/each}
	</Select.Content>
</Select.Root>
