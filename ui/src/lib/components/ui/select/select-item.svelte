<script lang="ts">
	import { Select as SelectPrimitive } from "bits-ui";
	import { cn } from "$lib/utils.js";
	import Check from "lucide-svelte/icons/check";

	let {
		ref = $bindable(null),
		class: className,
		value,
		label,
		...restProps
	}: SelectPrimitive.ItemProps & { label?: string } = $props();
</script>

<SelectPrimitive.Item
	bind:ref
	{value}
	class={cn(
		"focus:bg-accent focus:text-accent-foreground relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[selected]:bg-accent",
		className
	)}
	{...restProps}
>
	{#snippet children({ selected })}
		<span class="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
			{#if selected}
				<Check class="h-4 w-4" />
			{/if}
		</span>
		{label ?? value}
	{/snippet}
</SelectPrimitive.Item>
