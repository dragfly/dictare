<script lang="ts">
	import { Button } from "$lib/components/ui/button";
	import KeyCaptureField from "./KeyCaptureField.svelte";
	import * as settingsStore from "$lib/stores/settings.svelte";

	function deepClone<T>(v: T): T { return JSON.parse(JSON.stringify(v)); }

	const COMMANDS: { value: string; label: string }[] = [
		{ value: "toggle-listening", label: "Toggle listening" },
		{ value: "listening-on",     label: "Start listening" },
		{ value: "listening-off",    label: "Stop listening" },
		{ value: "next-agent",       label: "Next agent" },
		{ value: "prev-agent",       label: "Previous agent" },
		{ value: "repeat",           label: "Repeat last" },
	];

	let rows = $state(deepClone(settingsStore.getShortcuts()));
	let initialized = false;

	// Sync rows from store when schema changes (after load()) and not dirty
	$effect(() => {
		const storeShortcuts = settingsStore.getShortcuts();
		if (!initialized) {
			rows = deepClone(storeShortcuts);
			initialized = true;
			return;
		}
		// When resetDirty() or load() clears dirtyShortcuts, revert
		if (settingsStore.getDirty() !== undefined) {
			// Check if shortcuts are not dirty — if so, sync from store
			const schema = settingsStore.getSchema();
			if (schema && JSON.stringify(rows) !== JSON.stringify(storeShortcuts)) {
				// Only sync if we're not dirty (dirtyShortcuts is null in store)
				const dirtyCheck = JSON.stringify(storeShortcuts) === JSON.stringify(schema.shortcuts);
				if (dirtyCheck || !settingsStore.hasDirtyFields()) {
					rows = deepClone(storeShortcuts);
				}
			}
		}
	});

	function addRow() {
		rows = [...rows, { keys: "", command: "toggle-listening" }];
		settingsStore.markShortcutsDirty(rows);
	}

	function removeRow(i: number) {
		rows = rows.filter((_, idx) => idx !== i);
		settingsStore.markShortcutsDirty(rows);
	}

	function updateKeys(i: number, keys: string) {
		rows = rows.map((r, idx) => (idx === i ? { ...r, keys } : r));
		settingsStore.markShortcutsDirty(rows);
	}

	function updateCommand(i: number, command: string) {
		rows = rows.map((r, idx) => (idx === i ? { ...r, command } : r));
		settingsStore.markShortcutsDirty(rows);
	}
</script>

<div class="flex flex-col gap-3 mb-6">
	<span class="text-xs font-medium text-muted-foreground uppercase tracking-wider">
		Shortcuts
	</span>

	{#if rows.length === 0}
		<p class="text-sm text-muted-foreground text-center py-2">No shortcuts configured.</p>
	{/if}

	{#each rows as row, i (i)}
		<div class="flex items-center gap-2">
			<!-- Key combo -->
			<div class="shrink-0">
				<KeyCaptureField
					format="shortcut"
					value={row.keys}
					onchange={(v) => updateKeys(i, v)}
				/>
			</div>

			<span class="text-muted-foreground text-xs shrink-0">→</span>

			<!-- Command -->
			<select
				class="flex-1 h-8 text-sm rounded-md border border-input bg-background px-2 text-foreground"
				value={row.command}
				onchange={(e) => updateCommand(i, e.currentTarget.value)}
			>
				{#each COMMANDS as cmd}
					<option value={cmd.value}>{cmd.label}</option>
				{/each}
			</select>

			<!-- Delete -->
			<button
				class="h-7 w-7 flex items-center justify-center rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors shrink-0"
				onclick={() => removeRow(i)}
				aria-label="Remove shortcut"
			>×</button>
		</div>
	{/each}

	<Button variant="outline" size="sm" onclick={addRow} class="w-full">
		+ Add shortcut
	</Button>
</div>
