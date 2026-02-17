<script lang="ts">
	import { Button } from "$lib/components/ui/button";
	import * as settingsStore from "$lib/stores/settings.svelte";

	const hasDirty = $derived(settingsStore.hasDirtyFields());
	const status = $derived(settingsStore.getSaveStatus());
</script>

<div class="sticky bottom-0 border-t bg-background/95 backdrop-blur py-3 mt-8 flex items-center gap-3">
	<Button
		disabled={!hasDirty || status === "saving"}
		onclick={() => settingsStore.saveAll()}
		size="sm"
	>
		{status === "saving" ? "Saving..." : "Save Changes"}
	</Button>
	{#if status === "saved"}
		<span class="text-sm text-green-400">Saved</span>
	{:else if status === "error"}
		<span class="text-sm text-destructive">Some fields had errors</span>
	{/if}
</div>
