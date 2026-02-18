<script lang="ts">
	import SettingsNav from "./SettingsNav.svelte";
	import SettingsSection from "./SettingsSection.svelte";
	import RestartBanner from "./RestartBanner.svelte";
	import SaveBar from "./SaveBar.svelte";
	import type { TabDef, NavChild } from "$lib/types";
	import * as settingsStore from "$lib/stores/settings.svelte";
	import { onMount } from "svelte";

	interface Props {
		tabs: TabDef[];
	}

	let { tabs }: Props = $props();

	// Default to the first leaf: if first tab has children, select first child
	function defaultNavId(): string {
		const first = tabs[0];
		if (!first) return "";
		return first.children ? first.children[0].id : first.id;
	}

	let activeNavId = $state(defaultNavId());

	onMount(() => {
		settingsStore.load();
	});

	const schema = $derived(settingsStore.getSchema());

	/**
	 * Resolve the active view from activeNavId.
	 * Returns { tab, child? } — child is set when a sub-item is active.
	 */
	const activeView = $derived((): { tab: TabDef; child?: NavChild } | null => {
		for (const tab of tabs) {
			if (tab.children) {
				const child = tab.children.find((c) => c.id === activeNavId);
				if (child) return { tab, child };
			} else if (tab.id === activeNavId) {
				return { tab };
			}
		}
		return null;
	});

	const activeSections = $derived(activeView()?.child?.sections ?? activeView()?.tab.sections ?? []);
	const activeLabel   = $derived(activeView()?.child?.label   ?? activeView()?.tab.label   ?? "");
	const activeDesc    = $derived(activeView()?.child?.desc    ?? activeView()?.tab.desc    ?? "");
</script>

<div class="flex h-screen">
	<SettingsNav {tabs} bind:activeNavId version={schema?.version ?? ""} />
	<main class="flex-1 overflow-y-auto">
		<div class="max-w-2xl mx-auto pt-14 pb-8">
			<RestartBanner />
			{#if activeView() && schema}
				<div class="px-4 mb-8">
					<h2 class="text-xl font-semibold mb-1.5">{activeLabel}</h2>
					<p class="text-sm text-muted-foreground">{activeDesc}</p>
				</div>
				<SettingsSection sections={activeSections} isGeneral={activeNavId === "general"} {schema} />
			{:else}
				<div class="text-muted-foreground py-20 text-center text-sm">Loading settings...</div>
			{/if}
			<SaveBar />
		</div>
	</main>
</div>
