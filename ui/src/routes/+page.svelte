<script lang="ts">
	import { onMount } from "svelte";
	import SettingsLayout from "$lib/components/settings/SettingsLayout.svelte";
	import { tabs } from "$lib/registry/tabs";
	import { initTabGuard, isEvicted } from "$lib/stores/tab-guard.svelte";

	onMount(() => {
		initTabGuard();
	});
</script>

<svelte:head>
	<title>Dictare Settings</title>
</svelte:head>

{#if isEvicted()}
	<div class="flex items-center justify-center h-screen bg-zinc-950">
		<p class="text-zinc-500 text-sm">Settings moved to another tab.</p>
	</div>
{:else}
	<SettingsLayout {tabs} />
{/if}
