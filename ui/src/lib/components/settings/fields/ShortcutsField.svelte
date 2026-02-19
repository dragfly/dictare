<script lang="ts">
	import { onMount } from "svelte";
	import { Button } from "$lib/components/ui/button";
	import KeyCaptureField from "./KeyCaptureField.svelte";
	import { fetchShortcuts, saveShortcuts, type Shortcut } from "$lib/api";

	const COMMANDS: { value: string; label: string }[] = [
		{ value: "toggle-listening", label: "Toggle listening" },
		{ value: "listening-on",     label: "Start listening" },
		{ value: "listening-off",    label: "Stop listening" },
		{ value: "next-agent",       label: "Next agent" },
		{ value: "prev-agent",       label: "Previous agent" },
		{ value: "repeat",           label: "Repeat last" },
	];

	let rows = $state<Shortcut[]>([]);
	let originalRows: Shortcut[] = [];
	let status = $state<"idle" | "loading" | "saving" | "saved" | "error">("loading");
	let errorMessage = $state("");
	let isOpen = $state(false);
	let loaded = false;

	const isDirty = $derived(
		status !== "loading" && JSON.stringify(rows) !== JSON.stringify(originalRows)
	);

	// Auto-dismiss "saved" feedback
	$effect(() => {
		if (status === "saved") {
			const t = setTimeout(() => (status = "idle"), 3000);
			return () => clearTimeout(t);
		}
	});

	async function toggle() {
		isOpen = !isOpen;
		if (isOpen && !loaded) {
			await load();
			loaded = true;
		}
	}

	async function load() {
		status = "loading";
		errorMessage = "";
		try {
			const data = await fetchShortcuts();
			originalRows = structuredClone(data);
			rows = structuredClone(data);
			status = "idle";
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : "Load failed";
			status = "error";
		}
	}

	function addRow() {
		rows = [...rows, { keys: "", command: "toggle-listening" }];
	}

	function removeRow(i: number) {
		rows = rows.filter((_, idx) => idx !== i);
	}

	function updateKeys(i: number, keys: string) {
		rows = rows.map((r, idx) => (idx === i ? { ...r, keys } : r));
	}

	function updateCommand(i: number, command: string) {
		rows = rows.map((r, idx) => (idx === i ? { ...r, command } : r));
	}

	async function save() {
		if (!isDirty) return;
		const valid = rows.filter((r) => r.keys && r.command);
		status = "saving";
		errorMessage = "";
		try {
			await saveShortcuts(valid);
			originalRows = structuredClone(valid);
			rows = structuredClone(valid);
			status = "saved";
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : "Save failed";
			status = "error";
		}
	}

	function reset() {
		if (!isDirty) return;
		rows = structuredClone(originalRows);
		status = "idle";
		errorMessage = "";
	}
</script>

<div class="border rounded-md overflow-hidden">
	<!-- Accordion header -->
	<button
		class="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-muted/40 transition-colors"
		onclick={toggle}
	>
		<span class="text-xs font-medium text-muted-foreground uppercase tracking-wider">
			Shortcuts
		</span>
		<svg
			class="h-4 w-4 text-muted-foreground transition-transform duration-200 {isOpen ? 'rotate-180' : ''}"
			xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"
		>
			<path fill-rule="evenodd" d="M5.22 8.22a.75.75 0 0 1 1.06 0L10 11.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 9.28a.75.75 0 0 1 0-1.06z" clip-rule="evenodd" />
		</svg>
	</button>

	{#if isOpen || loaded}
		<div class="border-t flex flex-col gap-3 px-4 pb-4 pt-3 {isOpen ? '' : 'hidden'}">
			<!-- Toolbar -->
			<div class="flex items-center justify-end gap-2">
				{#if status === "saved"}
					<span class="text-xs text-green-500">Saved</span>
				{:else if status === "error"}
					<span class="text-xs text-destructive">Error</span>
				{/if}
				<Button
					variant="ghost" size="sm"
					disabled={!isDirty || status === "saving"}
					onclick={reset}
				>Reset</Button>
				<Button
					size="sm"
					disabled={!isDirty || status === "saving"}
					onclick={save}
				>{status === "saving" ? "Saving…" : "Save"}</Button>
			</div>

			<!-- Rows -->
			{#if status === "loading"}
				<p class="text-sm text-muted-foreground text-center py-2 animate-pulse">Loading…</p>
			{:else}
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
			{/if}

			{#if status === "error" && errorMessage}
				<p class="text-xs text-destructive font-mono whitespace-pre-wrap">{errorMessage}</p>
			{/if}
		</div>
	{/if}
</div>
