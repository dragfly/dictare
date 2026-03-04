<script lang="ts">
	import { tick, onMount, onDestroy } from "svelte";
	import { EditorState } from "@codemirror/state";
	import {
		EditorView,
		keymap,
		highlightActiveLine,
		drawSelection,
		highlightSpecialChars,
		dropCursor,
	} from "@codemirror/view";
	import { StreamLanguage, syntaxHighlighting } from "@codemirror/language";
	import { toml } from "@codemirror/legacy-modes/mode/toml";
	import { classHighlighter } from "@lezer/highlight";
	import { history, defaultKeymap, historyKeymap } from "@codemirror/commands";
	import * as settingsStore from "$lib/stores/settings.svelte";

	interface Props {
		section: string;
		label: string;
		noAccordion?: boolean;
	}

	let { section, label, noAccordion = false }: Props = $props();

	let editorEl: HTMLDivElement;
	let view: EditorView | null = null;
	let currentContent = $state("");
	let isOpen = $state(false);
	let loaded = false;

	/** The original content from the store (not dirty). */
	function originalContent(): string {
		return settingsStore.getSchema()?.toml_sections[section] ?? "";
	}

	const extensions = [
		highlightSpecialChars(),
		history(),
		drawSelection(),
		dropCursor(),
		highlightActiveLine(),
		keymap.of([...defaultKeymap, ...historyKeymap]),
		StreamLanguage.define(toml),
		syntaxHighlighting(classHighlighter),
		EditorView.updateListener.of((update) => {
			if (update.docChanged) {
				currentContent = update.state.doc.toString();
				// Track dirty state in the global store
				if (currentContent !== originalContent()) {
					settingsStore.markTomlDirty(section, currentContent);
				} else {
					settingsStore.markTomlClean(section);
				}
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

	// When resetDirty() clears dirtyToml, revert editor content
	$effect(() => {
		const dirtyToml = settingsStore.getDirtyToml();
		if (loaded && view && !(section in dirtyToml) && currentContent !== originalContent()) {
			const content = originalContent();
			view.dispatch({
				changes: { from: 0, to: view.state.doc.length, insert: content }
			});
		}
	});

	// When schema changes (after load()), update editor with new content
	$effect(() => {
		const s = settingsStore.getSchema();
		if (!loaded || !view || !s) return;
		// Only update if this section is not dirty
		if (section in settingsStore.getDirtyToml()) return;
		const content = s.toml_sections[section] ?? "";
		if (content !== currentContent) {
			view.dispatch({
				changes: { from: 0, to: view.state.doc.length, insert: content }
			});
		}
	});

	onMount(() => {
		if (noAccordion) {
			isOpen = true;
			tick().then(() => {
				initEditor();
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
			initEditor();
			loaded = true;
		}
	}

	function initEditor() {
		const content = settingsStore.getTomlSection(section);
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
	}
</script>

{#if noAccordion}
	<!-- No accordion: title + editor always visible -->
	<div class="flex flex-col gap-3 mb-6">
		<span class="text-xs font-medium text-muted-foreground uppercase tracking-wider">
			{label}
		</span>

		<!-- CodeMirror editor mount point -->
		<div
			bind:this={editorEl}
			class="rounded-md border bg-muted/30 overflow-hidden"
		></div>
	</div>
{:else}
	<!-- Accordion mode -->
	<div class="border rounded-md overflow-hidden mb-2">
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

		{#if isOpen || loaded}
			<div class="border-t flex flex-col gap-3 px-4 pb-4 pt-3 {isOpen ? '' : 'hidden'}">
				<!-- CodeMirror editor mount point -->
				<div
					bind:this={editorEl}
					class="rounded-md border bg-muted/30 overflow-hidden"
				></div>
			</div>
		{/if}
	</div>
{/if}
