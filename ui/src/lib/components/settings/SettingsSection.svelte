<script lang="ts">
	import type { TabDef, SchemaResponse, FieldMeta } from "$lib/types";
	import FieldRenderer from "./FieldRenderer.svelte";

	interface Props {
		tab: TabDef;
		schema: SchemaResponse;
	}

	let { tab, schema }: Props = $props();

	const SKIP_KEYS = new Set(["keyboard.shortcuts"]);

	const allFields = $derived(
		schema.keys.filter((k) => {
			if (SKIP_KEYS.has(k.key)) return false;
			if (tab.id === "general") return !k.key.includes(".");
			const section = k.key.split(".")[0];
			return tab.sections.includes(section);
		})
	);

	/** Group fields according to tab.groups definition */
	const groups = $derived(() => {
		if (!tab.groups) return null;
		return tab.groups.map((g) => ({
			label: g.label,
			fields: allFields.filter((f) => {
				const section = f.key.split(".")[0];
				return g.sections.includes(section);
			}),
		})).filter((g) => g.fields.length > 0);
	});
</script>

{#if allFields.length === 0}
	<div class="text-sm text-muted-foreground py-8 text-center">
		No configurable fields in this section.
	</div>
{:else if groups()}
	<!-- Grouped layout from UI hints -->
	{#each groups()! as group, i (group.label)}
		{#if i > 0}
			<div class="h-px bg-border my-4"></div>
		{/if}
		<div class="mb-2 px-4">
			<h3 class="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
				{group.label}
			</h3>
		</div>
		<div class="space-y-1">
			{#each group.fields as field (field.key)}
				<FieldRenderer {field} schema={schema.schema} />
			{/each}
		</div>
	{/each}
{:else}
	<!-- Flat layout -->
	<div class="space-y-1">
		{#each allFields as field (field.key)}
			<FieldRenderer {field} schema={schema.schema} />
		{/each}
	</div>
{/if}
