<script lang="ts">
	import type { TabDef, SchemaResponse } from "$lib/types";
	import FieldRenderer from "./FieldRenderer.svelte";

	interface Props {
		tab: TabDef;
		schema: SchemaResponse;
	}

	let { tab, schema }: Props = $props();

	const SKIP_KEYS = new Set(["keyboard.shortcuts"]);

	const fields = $derived(
		schema.keys.filter((k) => {
			if (SKIP_KEYS.has(k.key)) return false;
			if (tab.id === "general") return !k.key.includes(".");
			const section = k.key.split(".")[0];
			return tab.sections.includes(section);
		})
	);
</script>

{#if fields.length === 0}
	<div class="text-sm text-muted-foreground py-8 text-center">
		No configurable fields in this section.
	</div>
{:else}
	<div class="space-y-1">
		{#each fields as field (field.key)}
			<FieldRenderer {field} schema={schema.schema} />
		{/each}
	</div>
{/if}
