<script lang="ts">
	import SettingsNav from "./SettingsNav.svelte";
	import SettingsSection from "./SettingsSection.svelte";
	import RestartBanner from "./RestartBanner.svelte";
	import SaveBar from "./SaveBar.svelte";
	import type { TabDef } from "$lib/types";
	import * as settingsStore from "$lib/stores/settings.svelte";
	import { onMount } from "svelte";

	interface Props {
		tabs: TabDef[];
	}

	let { tabs }: Props = $props();
	let activeTabId = $state(tabs[0]?.id ?? "");

	onMount(() => {
		settingsStore.load();
	});

	const activeTab = $derived(tabs.find((t) => t.id === activeTabId));
	const schema = $derived(settingsStore.getSchema());
</script>

<div class="flex h-screen">
	<SettingsNav {tabs} bind:activeTabId version={schema?.version ?? ""} />
	<main class="flex-1 overflow-y-auto">
		<div class="max-w-2xl mx-auto px-8 py-6">
			<RestartBanner />
			{#if activeTab && schema}
				<h2 class="text-lg font-semibold mb-1">{activeTab.label}</h2>
				<p class="text-sm text-muted-foreground mb-6">{activeTab.desc}</p>
				<SettingsSection tab={activeTab} {schema} />
			{:else}
				<div class="text-muted-foreground py-20 text-center text-sm">Loading settings...</div>
			{/if}
			<SaveBar />
		</div>
	</main>
</div>
