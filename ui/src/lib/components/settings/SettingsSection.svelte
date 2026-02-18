<script lang="ts">
	import type { TabDef, SchemaResponse } from "$lib/types";
	import FieldRenderer from "./FieldRenderer.svelte";
	import { ChevronRight } from "lucide-svelte";

	interface Props {
		tab: TabDef;
		schema: SchemaResponse;
	}

	let { tab, schema }: Props = $props();

	// keyboard.shortcuts is shown via TomlField in the Hotkey tab
	// default_agent_type is part of the agent_types TOML editor (Agents tab)
	const SKIP_KEYS = new Set(["default_agent_type"]);

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
	<!-- Accordion layout for grouped tabs -->
	<div class="space-y-1">
		{#each groups()! as group (group.label)}
			<details class="group/acc rounded-lg border border-transparent hover:border-border transition-colors open:border-border">
				<summary class="
					flex items-center gap-2 px-4 py-3 cursor-pointer select-none
					list-none rounded-lg
					hover:bg-accent/40 transition-colors
				">
					<ChevronRight
						class="size-3.5 text-muted-foreground transition-transform duration-200 group-open/acc:rotate-90"
					/>
					<span class="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
						{group.label}
					</span>
					<span class="ml-auto text-xs text-muted-foreground/50">
						{group.fields.length} {group.fields.length === 1 ? "field" : "fields"}
					</span>
				</summary>

				<div class="pb-2 space-y-1">
					{#each group.fields as field (field.key)}
						<FieldRenderer {field} schema={schema.schema} />
					{/each}
				</div>
			</details>
		{/each}
	</div>
{:else}
	<!-- Flat layout for single-section tabs -->
	<div class="space-y-1">
		{#each allFields as field (field.key)}
			<FieldRenderer {field} schema={schema.schema} />
		{/each}
	</div>
{/if}
