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

	const isFloat = $derived(step !== 1);
	const pattern = $derived(isFloat ? "[0-9.\\-]*" : "[0-9\\-]*");

	function filterInput(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		const allowed = isFloat ? /[^0-9.\-]/g : /[^0-9\-]/g;
		const filtered = input.value.replace(allowed, "");
		if (filtered !== input.value) {
			input.value = filtered;
		}
	}
</script>

<Input
	type="text"
	inputmode="numeric"
	{pattern}
	class="{widthClass} text-right"
	value={value ?? ""}
	oninput={filterInput}
	onchange={(e) => {
		const raw = e.currentTarget.value.trim();
		const v = isFloat ? parseFloat(raw) : parseInt(raw, 10);
		if (!isNaN(v)) onchange(v);
	}}
/>
