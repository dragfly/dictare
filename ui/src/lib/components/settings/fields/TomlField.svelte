<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import { EditorState } from "@codemirror/state";
	import { EditorView, basicSetup } from "codemirror";
	import { StreamLanguage } from "@codemirror/language";
	import { toml } from "@codemirror/legacy-modes/mode/toml";
	import { Button } from "$lib/components/ui/button";
	import { fetchTomlSection, saveTomlSection } from "$lib/api";

	interface Props {
		section: string;
		label: string;
	}

	let { section, label }: Props = $props();

	let editorEl: HTMLDivElement;
	let view: EditorView | null = null;
	let status = $state<"loading" | "idle" | "saving" | "saved" | "error">("loading");
	let errorMessage = $state("");
	let originalContent = $state("");

	const isDark = $derived(
		typeof document !== "undefined" &&
		document.documentElement.classList.contains("dark")
	);

	// Auto-dismiss "saved" feedback
	$effect(() => {
		if (status === "saved") {
			const t = setTimeout(() => (status = "idle"), 3000);
			return () => clearTimeout(t);
		}
	});

	onMount(async () => {
		await reload();
	});

	onDestroy(() => {
		view?.destroy();
	});

	async function reload() {
		status = "loading";
		errorMessage = "";
		try {
			const content = await fetchTomlSection(section);
			originalContent = content;
			if (view) {
				view.dispatch({
					changes: { from: 0, to: view.state.doc.length, insert: content }
				});
			} else {
				view = new EditorView({
					state: EditorState.create({
						doc: content,
						extensions: [
							basicSetup,
							StreamLanguage.define(toml),
							EditorView.theme({
								"&": { fontSize: "12.5px", fontFamily: "monospace" },
								".cm-editor": { borderRadius: "0.375rem" },
								".cm-scroller": { minHeight: "180px", maxHeight: "480px", overflow: "auto" },
							}),
						]
					}),
					parent: editorEl
				});
			}
			status = "idle";
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : "Load failed";
			status = "error";
		}
	}

	async function save() {
		if (!view) return;
		status = "saving";
		errorMessage = "";
		const content = view.state.doc.toString();
		try {
			await saveTomlSection(section, content);
			originalContent = content;
			status = "saved";
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : "Save failed";
			status = "error";
		}
	}

	function reset() {
		if (!view) return;
		view.dispatch({
			changes: { from: 0, to: view.state.doc.length, insert: originalContent }
		});
		status = "idle";
		errorMessage = "";
	}
</script>

<div class="flex flex-col gap-3 py-3 px-1">
	<div class="flex items-center justify-between">
		<span class="text-sm font-medium text-muted-foreground uppercase tracking-wider text-xs">
			{label}
		</span>
		<div class="flex items-center gap-2">
			{#if status === "saved"}
				<span class="text-xs text-green-500">Saved</span>
			{:else if status === "error"}
				<span class="text-xs text-destructive">Error</span>
			{/if}
			<Button
				variant="ghost"
				size="sm"
				disabled={status === "loading" || status === "saving"}
				onclick={reset}
			>
				Reset
			</Button>
			<Button
				size="sm"
				disabled={status === "loading" || status === "saving"}
				onclick={save}
			>
				{status === "saving" ? "Saving…" : "Save"}
			</Button>
		</div>
	</div>

	<!-- CodeMirror editor mount point -->
	<div
		bind:this={editorEl}
		class="rounded-md border bg-muted/30 overflow-hidden
			{status === 'loading' ? 'opacity-50' : ''}"
	></div>

	{#if status === "error" && errorMessage}
		<p class="text-xs text-destructive font-mono whitespace-pre-wrap">{errorMessage}</p>
	{/if}
</div>
