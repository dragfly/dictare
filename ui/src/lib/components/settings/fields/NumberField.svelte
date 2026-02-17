<script lang="ts">
	import { Input } from "$lib/components/ui/input";

	interface Props {
		value: number | null;
		step: number;
		size?: "narrow" | "medium" | "normal";
		onchange: (value: number) => void;
	}

	let { value, step = 1, size = "normal", onchange }: Props = $props();

	const widthClass = $derived(
		size === "narrow" ? "w-20" : size === "medium" ? "w-24" : "w-28"
	);
</script>

<Input
	type="number"
	class="hide-spinners {widthClass} text-right"
	{step}
	value={value ?? ""}
	onchange={(e) => {
		const v = step === 1 ? parseInt(e.currentTarget.value, 10) : parseFloat(e.currentTarget.value);
		if (!isNaN(v)) onchange(v);
	}}
/>

<style>
	:global(.hide-spinners::-webkit-inner-spin-button),
	:global(.hide-spinners::-webkit-outer-spin-button) {
		-webkit-appearance: none;
		margin: 0;
		display: none;
	}
	:global(.hide-spinners) {
		-moz-appearance: textfield;
	}
</style>
