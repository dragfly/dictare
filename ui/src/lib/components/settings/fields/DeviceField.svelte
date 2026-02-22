<script lang="ts">
	import * as Select from "$lib/components/ui/select";
	import { fetchAudioDevices, type AudioDeviceInfo } from "$lib/api";

	interface Props {
		direction: "input" | "output";
		value: string;
		onchange: (value: string) => void;
	}

	let { direction, value, onchange }: Props = $props();

	let devices = $state<AudioDeviceInfo[]>([]);
	let defaultDevice = $state<AudioDeviceInfo | null>(null);
	let loaded = $state(false);

	const SENTINEL = "__default__";

	$effect(() => {
		fetchAudioDevices()
			.then((resp) => {
				devices = direction === "input" ? resp.input : resp.output;
				defaultDevice =
					direction === "input" ? resp.default_input : resp.default_output;
				loaded = true;
			})
			.catch(() => {
				loaded = true;
			});
	});

	const defaultLabel = $derived(
		defaultDevice ? `Default (${defaultDevice.name})` : "Default"
	);

	const deviceNames = $derived(devices.map((d) => d.name));

	const displayValue = $derived(
		!value || !deviceNames.includes(value) ? SENTINEL : value
	);

	const displayLabel = $derived(
		displayValue === SENTINEL ? defaultLabel : value
	);

	function handleChange(v: string) {
		if (v === SENTINEL) {
			onchange("");
		} else {
			onchange(v);
		}
	}
</script>

{#if !loaded}
	<span class="text-xs text-muted-foreground">Loading...</span>
{:else}
	<Select.Root
		type="single"
		value={displayValue}
		onValueChange={(v) => {
			if (v) handleChange(v);
		}}
	>
		<Select.Trigger class="w-fit max-w-64 whitespace-nowrap">
			<span class="truncate">{displayLabel}</span>
		</Select.Trigger>
		<Select.Content>
			<Select.Item value={SENTINEL} label={defaultLabel} />
			{#each devices as dev (dev.index)}
				<Select.Item value={dev.name} label={dev.name} />
			{/each}
		</Select.Content>
	</Select.Root>
{/if}
