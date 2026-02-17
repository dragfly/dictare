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
	class="{widthClass} text-right"
	{step}
	value={value ?? ""}
	onchange={(e) => {
		const v = step === 1 ? parseInt(e.currentTarget.value, 10) : parseFloat(e.currentTarget.value);
		if (!isNaN(v)) onchange(v);
	}}
/>
