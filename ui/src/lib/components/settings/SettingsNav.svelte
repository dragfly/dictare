<script lang="ts">
	import type { TabDef } from "$lib/types";
	import { Separator } from "$lib/components/ui/separator";
	import { ChevronRight } from "lucide-svelte";

	interface Props {
		tabs: TabDef[];
		activeNavId: string;
		version: string;
	}

	let { tabs, activeNavId = $bindable(), version }: Props = $props();

	/** Set of expanded parent IDs (expandable tabs whose children are visible). */
	let expanded = $state<Set<string>>(new Set());

	/** On mount: expand the parent of the initial active item. */
	$effect(() => {
		for (const tab of tabs) {
			if (tab.children) {
				if (tab.children.some((c) => c.id === activeNavId) || tab.id === activeNavId) {
					expanded = new Set([...expanded, tab.id]);
				}
			}
		}
	});

	function toggleExpand(tabId: string) {
		const next = new Set(expanded);
		if (next.has(tabId)) {
			next.delete(tabId);
		} else {
			next.add(tabId);
		}
		expanded = next;
	}

	function selectLeaf(id: string) {
		activeNavId = id;
	}

	function isActive(id: string): boolean {
		return activeNavId === id;
	}

	function parentIsActive(tab: TabDef): boolean {
		if (!tab.children) return false;
		return tab.children.some((c) => c.id === activeNavId);
	}
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
			{#if tab.children}
				<!-- Expandable parent -->
				<button
					class="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors
						{parentIsActive(tab)
							? 'text-accent-foreground font-medium'
							: 'text-muted-foreground hover:bg-accent/50 hover:text-accent-foreground'}"
					onclick={() => toggleExpand(tab.id)}
				>
					<Icon class="size-4 shrink-0" />
					<span class="flex-1 text-left">{tab.label}</span>
					<ChevronRight
						class="size-3.5 transition-transform duration-150 {expanded.has(tab.id) ? 'rotate-90' : ''}"
					/>
				</button>

				<!-- Children -->
				{#if expanded.has(tab.id)}
					<div class="ml-3 pl-3 border-l border-border/60 space-y-0.5 py-0.5">
						{#each tab.children as child (child.id)}
							<button
								class="flex w-full items-center rounded-md px-3 py-1.5 text-sm transition-colors
									{isActive(child.id)
										? 'bg-accent text-accent-foreground font-medium'
										: 'text-muted-foreground hover:bg-accent/50 hover:text-accent-foreground'}"
								onclick={() => selectLeaf(child.id)}
							>
								{child.label}
							</button>
						{/each}
					</div>
				{/if}
			{:else}
				<!-- Simple leaf item -->
				<button
					class="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors
						{isActive(tab.id)
							? 'bg-accent text-accent-foreground font-medium'
							: 'text-muted-foreground hover:bg-accent/50 hover:text-accent-foreground'}"
					onclick={() => selectLeaf(tab.id)}
				>
					<Icon class="size-4 shrink-0" />
					{tab.label}
				</button>
			{/if}
		{/each}
	</div>
</nav>
