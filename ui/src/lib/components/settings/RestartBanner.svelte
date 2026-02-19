<script lang="ts">
	import { Button } from "$lib/components/ui/button";
	import { RotateCcw } from "lucide-svelte";
	import * as settingsStore from "$lib/stores/settings.svelte";
	import { restartEngine, pingEngine } from "$lib/api";

	const show = $derived(settingsStore.getNeedsRestart());
	let restarting = $state(false);

	async function handleRestart() {
		restarting = true;
		await restartEngine();
		// Poll until the engine responds, then auto-dismiss
		while (true) {
			await new Promise<void>((r) => setTimeout(r, 1000));
			const alive = await pingEngine();
			if (alive) {
				settingsStore.clearNeedsRestart();
				break;
			}
		}
		restarting = false;
	}
</script>

{#if show}
	<div class="flex items-center gap-3 rounded-lg border bg-secondary/50 px-4 py-3 mb-6 text-sm">
		{#if restarting}
			<span class="text-muted-foreground animate-pulse">Engine is restarting…</span>
		{:else}
			<span class="flex-1">Changes saved. Restart the engine for changes to take effect.</span>
			<Button size="sm" variant="outline" onclick={handleRestart}>
				<RotateCcw class="size-3.5 mr-1.5" />
				Restart Engine
			</Button>
		{/if}
	</div>
{/if}
