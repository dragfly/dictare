<script lang="ts">
	import type { TabDef, SchemaResponse, FieldMeta } from "$lib/types";
	import FieldRenderer from "./FieldRenderer.svelte";

	interface Props {
		tab: TabDef;
		schema: SchemaResponse;
	}

	let { tab, schema }: Props = $props();

	const SKIP_KEYS = new Set(["keyboard.shortcuts"]);

	/** Capitalize a section name for display */
	function sectionTitle(section: string): string {
		return section.replace(/\b\w/g, (c) => c.toUpperCase());
	}

	const fields = $derived(
		schema.keys.filter((k) => {
			if (SKIP_KEYS.has(k.key)) return false;
			if (tab.id === "general") return !k.key.includes(".");
			const section = k.key.split(".")[0];
			return tab.sections.includes(section);
		})
	);

	/** Group fields by section prefix — preserves order */
	const groupedFields = $derived(() => {
		if (tab.sections.length <= 1) return null;
		const groups: { section: string; fields: FieldMeta[] }[] = [];
		let currentSection = "";
		for (const field of fields) {
			const section = field.key.split(".")[0] || "";
			if (section !== currentSection) {
				currentSection = section;
				groups.push({ section, fields: [] });
			}
			groups[groups.length - 1].fields.push(field);
		}
		return groups;
	});
</script>

{#if fields.length === 0}
	<div class="text-sm text-muted-foreground py-8 text-center">
		No configurable fields in this section.
	</div>
{:else if groupedFields()}
	<!-- Multi-section tab: show section headers -->
	{#each groupedFields()! as group, i (group.section)}
		{#if i > 0}
			<div class="h-px bg-border my-4"></div>
		{/if}
		<div class="mb-2 px-4">
			<h3 class="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
				{sectionTitle(group.section)}
			</h3>
		</div>
		<div class="space-y-1">
			{#each group.fields as field (field.key)}
				<FieldRenderer {field} schema={schema.schema} />
			{/each}
		</div>
	{/each}
{:else}
	<!-- Single-section tab: flat list -->
	<div class="space-y-1">
		{#each fields as field (field.key)}
			<FieldRenderer {field} schema={schema.schema} />
		{/each}
	</div>
{/if}
