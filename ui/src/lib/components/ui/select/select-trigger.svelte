<script lang="ts">
	import { Select as SelectPrimitive } from "bits-ui";
	import { cn } from "$lib/utils.js";
	import ChevronDown from "lucide-svelte/icons/chevron-down";

	let {
		ref = $bindable(null),
		class: className,
		children,
		placeholder = "Select...",
		...restProps
	}: SelectPrimitive.TriggerProps & { placeholder?: string } = $props();

	const triggerClass = "border-input bg-background ring-offset-background focus:ring-ring flex h-10 w-full items-center justify-between rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50";
</script>

<SelectPrimitive.Trigger bind:ref {...restProps}>
	{#snippet child({ props })}
		<button {...props} class={cn(triggerClass, className)}>
			{#if children}
				{@render children()}
			{:else}
				<span class="text-muted-foreground">{placeholder}</span>
			{/if}
			<ChevronDown class="h-4 w-4 opacity-50 shrink-0" />
		</button>
	{/snippet}
</SelectPrimitive.Trigger>
