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
	type="text"
	inputmode="numeric"
	class="{widthClass} text-right"
	value={value ?? ""}
	onchange={(e) => {
		const raw = e.currentTarget.value.trim();
		const v = step === 1 ? parseInt(raw, 10) : parseFloat(raw);
		if (!isNaN(v)) onchange(v);
	}}
/>
