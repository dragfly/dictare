<script lang="ts">
	import { tick, onMount, onDestroy } from "svelte";
	import { EditorState } from "@codemirror/state";
	import {
		EditorView,
		keymap,
		lineNumbers,
		highlightActiveLine,
		drawSelection,
		highlightSpecialChars,
		dropCursor,
	} from "@codemirror/view";
	import { StreamLanguage, syntaxHighlighting } from "@codemirror/language";
	import { toml } from "@codemirror/legacy-modes/mode/toml";
	import { classHighlighter } from "@lezer/highlight";
	import { history, defaultKeymap, historyKeymap } from "@codemirror/commands";
	import { Button } from "$lib/components/ui/button";
	import { fetchTomlSection, saveTomlSection } from "$lib/api";

	interface Props {
		section: string;
		label: string;
		noAccordion?: boolean;
	}

	let { section, label, noAccordion = false }: Props = $props();

	let editorEl: HTMLDivElement;
	let view: EditorView | null = null;
	let status = $state<"loading" | "idle" | "saving" | "saved" | "error">("idle");
	let errorMessage = $state("");
	let originalContent = $state("");
	let currentContent = $state("");
	let isOpen = $state(false);
	let loaded = false;

	const isDirty = $derived(
		status !== "loading" && currentContent !== originalContent
	);

	const extensions = [
		highlightSpecialChars(),
		history(),
		drawSelection(),
		dropCursor(),
		lineNumbers(),
		highlightActiveLine(),
		keymap.of([...defaultKeymap, ...historyKeymap]),
		StreamLanguage.define(toml),
		syntaxHighlighting(classHighlighter),
		EditorView.updateListener.of((update) => {
			if (update.docChanged) {
				currentContent = update.state.doc.toString();
			}
		}),
		EditorView.theme({
			"& .tok-comment":  { color: "#6a9955", fontStyle: "normal" },
			"& .tok-heading":  { color: "#dcd43a", fontWeight: "normal", textDecoration: "none" },
			"&":               { fontSize: "12.5px", fontFamily: "monospace" },
			".cm-editor":      { borderRadius: "0.375rem" },
			".cm-scroller":    { minHeight: "180px", maxHeight: "480px", overflow: "auto" },
		}),
	];

	// Auto-dismiss "saved" feedback
	$effect(() => {
		if (status === "saved") {
			const t = setTimeout(() => (status = "idle"), 3000);
			return () => clearTimeout(t);
		}
	});

	onMount(() => {
		if (noAccordion) {
			isOpen = true;
			tick().then(() => {
				reload();
				loaded = true;
			});
		}
	});

	onDestroy(() => {
		view?.destroy();
	});

	async function toggle() {
		isOpen = !isOpen;
		if (isOpen && !loaded) {
			await tick(); // wait for editorEl to be in DOM
			await reload();
			loaded = true;
		}
	}

	async function reload() {
		status = "loading";
		errorMessage = "";
		try {
			const content = await fetchTomlSection(section);
			originalContent = content;
			currentContent = content;
			if (view) {
				view.dispatch({
					changes: { from: 0, to: view.state.doc.length, insert: content }
				});
			} else {
				view = new EditorView({
					state: EditorState.create({ doc: content, extensions }),
					parent: editorEl,
				});
			}
			status = "idle";
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : "Load failed";
			status = "error";
		}
	}

	async function save() {
		if (!view || !isDirty) return;
		status = "saving";
		errorMessage = "";
		const content = view.state.doc.toString();
		try {
			await saveTomlSection(section, content);
			originalContent = content;
			currentContent = content;
			status = "saved";
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : "Save failed";
			status = "error";
		}
	}

	function reset() {
		if (!view || !isDirty) return;
		view.dispatch({
			changes: { from: 0, to: view.state.doc.length, insert: originalContent }
		});
		// updateListener will set currentContent = originalContent → isDirty = false
		status = "idle";
		errorMessage = "";
	}
</script>

<div class="border rounded-md overflow-hidden">
	{#if !noAccordion}
		<!-- Accordion header -->
		<button
			class="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-muted/40 transition-colors"
			onclick={toggle}
		>
			<span class="text-xs font-medium text-muted-foreground uppercase tracking-wider">
				{label}
			</span>
			<svg
				class="h-4 w-4 text-muted-foreground transition-transform duration-200 {isOpen ? 'rotate-180' : ''}"
				xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"
			>
				<path fill-rule="evenodd" d="M5.22 8.22a.75.75 0 0 1 1.06 0L10 11.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 9.28a.75.75 0 0 1 0-1.06z" clip-rule="evenodd" />
			</svg>
		</button>
	{/if}

	<!-- Body: rendered lazily (accordion) or immediately (noAccordion) -->
	{#if isOpen || loaded}
		<div class="{noAccordion ? '' : 'border-t'} flex flex-col gap-3 px-4 pb-4 pt-3 {isOpen ? '' : 'hidden'}">
			<div class="flex items-center justify-end gap-2">
				{#if status === "saved"}
					<span class="text-xs text-green-500">Saved</span>
				{:else if status === "error"}
					<span class="text-xs text-destructive">Error</span>
				{/if}
				<Button
					variant="ghost"
					size="sm"
					disabled={!isDirty || status === "saving"}
					onclick={reset}
				>
					Reset
				</Button>
				<Button
					size="sm"
					disabled={!isDirty || status === "saving"}
					onclick={save}
				>
					{status === "saving" ? "Saving…" : "Save"}
				</Button>
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
	{/if}
</div>
