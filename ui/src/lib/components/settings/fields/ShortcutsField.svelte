<script lang="ts">
	import { onMount } from "svelte";
	import { Button } from "$lib/components/ui/button";
	import KeyCaptureField from "./KeyCaptureField.svelte";
	import { fetchShortcuts, saveShortcuts, type Shortcut } from "$lib/api";

	function deepClone<T>(v: T): T { return JSON.parse(JSON.stringify(v)); }

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

	onMount(() => { load(); });

	async function load() {
		status = "loading";
		errorMessage = "";
		try {
			const data = await fetchShortcuts();
			originalRows = deepClone(data);
			rows = deepClone(data);
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
			originalRows = deepClone(valid);
			rows = deepClone(valid);
			status = "saved";
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : "Save failed";
			status = "error";
		}
	}

	function reset() {
		if (!isDirty) return;
		rows = deepClone(originalRows);
		status = "idle";
		errorMessage = "";
	}
</script>

<div class="flex flex-col gap-3 mb-6">
	<span class="text-xs font-medium text-muted-foreground uppercase tracking-wider">
		Shortcuts
	</span>

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

	<div class="flex items-center gap-2">
		<Button
			size="sm"
			disabled={!isDirty || status === "saving"}
			onclick={save}
		>{status === "saving" ? "Saving…" : "Save"}</Button>
		<Button
			variant="ghost" size="sm"
			disabled={!isDirty || status === "saving"}
			onclick={reset}
		>Reset</Button>
		{#if status === "saved"}
			<span class="text-xs text-green-500">Saved</span>
		{:else if status === "error" && errorMessage}
			<span class="text-xs text-destructive">{errorMessage}</span>
		{/if}
	</div>
</div>
