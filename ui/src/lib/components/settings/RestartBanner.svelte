<script lang="ts">
	import { Button } from "$lib/components/ui/button";
	import { RotateCcw } from "lucide-svelte";
	import * as settingsStore from "$lib/stores/settings.svelte";
	import { restartEngine } from "$lib/api";

	const show = $derived(settingsStore.getNeedsRestart());
	let restarting = $state(false);

	async function handleRestart() {
		restarting = true;
		await restartEngine();
	}
</script>

{#if show}
	<div class="flex items-center gap-3 rounded-lg border bg-secondary/50 px-4 py-3 mb-6 text-sm">
		{#if restarting}
			<span class="text-muted-foreground">Engine is restarting... This page will stop working until the engine is back.</span>
		{:else}
			<span class="flex-1">Changes saved. Restart the engine for changes to take effect.</span>
			<Button size="sm" variant="outline" onclick={handleRestart}>
				<RotateCcw class="size-3.5 mr-1.5" />
				Restart Engine
			</Button>
		{/if}
	</div>
{/if}
