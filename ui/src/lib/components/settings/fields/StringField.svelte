<script lang="ts">
	import { Input } from "$lib/components/ui/input";

	interface Props {
		value: string;
		size?: "narrow" | "medium" | "normal";
		placeholder?: string;
		align?: "left" | "right";
		onchange: (value: string) => void;
	}

	let { value, size = "normal", placeholder = "", align = "left", onchange }: Props = $props();

	const widthClass = $derived(
		size === "narrow" ? "w-24" : size === "medium" ? "w-36" : "w-48"
	);
	const alignClass = $derived(align === "right" ? "text-right" : "");
</script>

<Input
	type="text"
	class="{widthClass} {alignClass}"
	{value}
	{placeholder}
	onchange={(e) => onchange(e.currentTarget.value)}
/>
