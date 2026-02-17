<script lang="ts">
	import type { TabDef } from "$lib/types";
	import { Separator } from "$lib/components/ui/separator";

	interface Props {
		tabs: TabDef[];
		activeTabId: string;
		version: string;
	}

	let { tabs, activeTabId = $bindable(), version }: Props = $props();
</script>

<nav class="w-52 shrink-0 border-r bg-background/50 h-screen overflow-y-auto p-3 flex flex-col">
	<div class="px-3 py-2 mb-1">
		<span class="text-sm font-semibold tracking-tight">VoxType</span>
		{#if version}
			<span class="text-[11px] text-muted-foreground ml-1.5">{version}</span>
		{/if}
	</div>
	<Separator class="mb-2" />
	<div class="space-y-0.5">
		{#each tabs as tab (tab.id)}
			{@const Icon = tab.icon}
			<button
				class="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors
					{activeTabId === tab.id
					? 'bg-accent text-accent-foreground font-medium'
					: 'text-muted-foreground hover:bg-accent/50 hover:text-accent-foreground'}"
				onclick={() => (activeTabId = tab.id)}
			>
				<Icon class="size-4 shrink-0" />
				{tab.label}
			</button>
		{/each}
	</div>
</nav>
