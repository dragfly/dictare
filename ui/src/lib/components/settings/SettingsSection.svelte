<script lang="ts">
	import type { SchemaResponse } from "$lib/types";
	import FieldRenderer from "./FieldRenderer.svelte";

	interface Props {
		sections: string[];
		isGeneral: boolean;
		schema: SchemaResponse;
	}

	let { sections, isGeneral, schema }: Props = $props();

	// default_agent_type is embedded in the agent_types TOML editor
	const SKIP_KEYS = new Set(["default_agent_type"]);

	const fields = $derived(
		schema.keys.filter((k) => {
			if (SKIP_KEYS.has(k.key)) return false;
			if (isGeneral) return !k.key.includes(".");
			const section = k.key.split(".")[0];
			return sections.includes(section);
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
