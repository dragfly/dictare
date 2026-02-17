<script lang="ts">
	import { Button } from "$lib/components/ui/button";
	import * as settingsStore from "$lib/stores/settings.svelte";

	const hasDirty = $derived(settingsStore.hasDirtyFields());
	const status = $derived(settingsStore.getSaveStatus());

	// Auto-dismiss "Saved" after 3 seconds
	$effect(() => {
		if (status === "saved") {
			const timer = setTimeout(() => settingsStore.clearSaveStatus(), 3000);
			return () => clearTimeout(timer);
		}
	});
</script>

{#if hasDirty || status === "saved" || status === "error"}
	<div class="sticky bottom-0 border-t bg-background/95 backdrop-blur py-3 mt-8 flex items-center gap-3 px-4">
		<Button
			disabled={!hasDirty || status === "saving"}
			onclick={() => settingsStore.saveAll()}
			size="sm"
		>
			{status === "saving" ? "Saving..." : "Save Changes"}
		</Button>
		{#if hasDirty}
			<Button
				variant="ghost"
				size="sm"
				onclick={() => settingsStore.resetDirty()}
			>
				Cancel
			</Button>
		{/if}
		{#if status === "saved"}
			<span class="text-sm text-green-400">Saved</span>
		{:else if status === "error"}
			<span class="text-sm text-destructive">Some fields had errors</span>
		{/if}
	</div>
{/if}
