<script lang="ts">
	import { Input } from "$lib/components/ui/input";

	interface Props {
		value: string;
		size?: "narrow" | "medium" | "normal";
		onchange: (value: string) => void;
	}

	let { value, size = "normal", onchange }: Props = $props();

	const widthClass = $derived(
		size === "narrow" ? "w-24" : size === "medium" ? "w-48" : "w-64"
	);
</script>

<Input
	type="text"
	class={widthClass}
	{value}
	onchange={(e) => onchange(e.currentTarget.value)}
/>
