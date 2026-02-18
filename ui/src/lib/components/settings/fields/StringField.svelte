<script lang="ts">
	import { Input } from "$lib/components/ui/input";

	interface Props {
		value: string;
		size?: "narrow" | "medium" | "normal";
		placeholder?: string;
		onchange: (value: string) => void;
	}

	let { value, size = "normal", placeholder = "", onchange }: Props = $props();

	const widthClass = $derived(
		size === "narrow" ? "w-24" : size === "medium" ? "w-36" : "w-48"
	);
</script>

<Input
	type="text"
	class={widthClass}
	{value}
	{placeholder}
	onchange={(e) => onchange(e.currentTarget.value)}
/>
