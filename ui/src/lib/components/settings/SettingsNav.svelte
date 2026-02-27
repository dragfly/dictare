<script lang="ts">
	import { untrack } from "svelte";
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

	/** When activeNavId changes, ensure the parent tab is expanded. */
	$effect(() => {
		for (const tab of tabs) {
			if (tab.children) {
				if (tab.children.some((c) => c.id === activeNavId) || tab.id === activeNavId) {
					// untrack: read expanded without creating a reactive dependency on it
					// (writing to expanded would otherwise re-trigger this effect → infinite loop)
					const current = untrack(() => expanded);
					if (!current.has(tab.id)) {
						expanded = new Set([...current, tab.id]);
					}
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
	<div class="px-3 pt-8 pb-3 mb-1 flex items-center gap-2">
		<svg width="24" height="24" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
			<rect x="0" y="0" width="100" height="100" rx="22" fill="#6d5ce6"/>
			<g transform="translate(0, 4)">
				<rect x="35" y="12" width="30" height="48" rx="15" fill="none" stroke="#FFFFFF" stroke-width="6"/>
				<path d="M 30 46 A 20 26 0 0 0 70 46" stroke="#FFFFFF" stroke-width="6" fill="none" stroke-linecap="round"/>
				<line x1="50" y1="72" x2="50" y2="82" stroke="#FFFFFF" stroke-width="6" stroke-linecap="round"/>
				<line x1="38" y1="82" x2="62" y2="82" stroke="#FFFFFF" stroke-width="6" stroke-linecap="round"/>
			</g>
		</svg>
		<span class="text-sm font-semibold tracking-tight">Dictare</span>
		{#if version}
			<span class="text-[11px] text-muted-foreground ml-1.5">{version}</span>
		{/if}
	</div>
	<Separator class="mb-3" />

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
