<script lang="ts">
	import type { SchemaResponse } from "$lib/types";
	import FieldRenderer from "./FieldRenderer.svelte";
	import { SECTION_EXTRA_FIELDS } from "$lib/registry/field-config";

	interface Props {
		sections: string[];
		isGeneral: boolean;
		schema: SchemaResponse;
	}

	let { sections, isGeneral, schema }: Props = $props();

	// default_agent_type is embedded in the agent_types TOML editor
	const SKIP_KEYS = new Set(["default_agent_type"]);

	const fields = $derived(
		(() => {
			const extraKeys = new Set(
				sections.flatMap((s) => SECTION_EXTRA_FIELDS[s] ?? [])
			);
			return schema.keys.filter((k) => {
				if (SKIP_KEYS.has(k.key)) return false;
				if (extraKeys.has(k.key)) return true;
				if (isGeneral) return !k.key.includes(".") && k.type !== "dict";
				const section = k.key.split(".")[0];
				return sections.includes(section);
			});
		})()
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
