<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import { Loader, CheckCircle, RotateCcw } from "lucide-svelte";
	import * as settingsStore from "$lib/stores/settings.svelte";
	import { restartEngine, pingEngine } from "$lib/api";

	type BarState = "hidden" | "restart-needed" | "restarting" | "ready";

	let barState = $state<BarState>("hidden");
	let wasDown = false;
	let timer: ReturnType<typeof setInterval> | null = null;
	let hideTimer: ReturnType<typeof setTimeout> | null = null;

	const needsRestart = $derived(settingsStore.getNeedsRestart());

	// When needsRestart becomes true, show the restart-needed bar
	$effect(() => {
		if (needsRestart && barState === "hidden") {
			barState = "restart-needed";
		}
	});

	async function handleRestart() {
		barState = "restarting";
		await restartEngine();
		// Wait for engine to go DOWN
		while (true) {
			await new Promise<void>((r) => setTimeout(r, 500));
			if (!(await pingEngine())) break;
		}
		// Wait for engine to come back UP
		while (true) {
			await new Promise<void>((r) => setTimeout(r, 1000));
			if (await pingEngine()) break;
		}
		settingsStore.clearNeedsRestart();
		barState = "ready";
		hideTimer = setTimeout(() => {
			barState = "hidden";
			hideTimer = null;
		}, 1500);
	}

	async function checkEngine(): Promise<boolean> {
		try {
			const r = await fetch("/health", { signal: AbortSignal.timeout(2000) });
			return r.ok;
		} catch {
			return false;
		}
	}

	async function poll() {
		const up = await checkEngine();

		if (!up) {
			wasDown = true;
			barState = "restarting";
			if (hideTimer) {
				clearTimeout(hideTimer);
				hideTimer = null;
			}
		} else if (wasDown) {
			// Engine just came back
			wasDown = false;
			settingsStore.clearNeedsRestart();
			barState = "ready";
			hideTimer = setTimeout(() => {
				barState = "hidden";
				hideTimer = null;
			}, 1500);
		}
		// If up and was never down, stay in current state
	}

	onMount(() => {
		// Start polling — first check after 1s, then every 2s
		setTimeout(poll, 1000);
		timer = setInterval(poll, 2000);
	});

	onDestroy(() => {
		if (timer) clearInterval(timer);
		if (hideTimer) clearTimeout(hideTimer);
	});
</script>

{#if barState !== "hidden"}
	<div
		class="fixed bottom-0 left-0 right-0 z-50 transition-all duration-300
			{barState === 'restart-needed'
				? 'border-t border-amber-500/30 bg-amber-950/90 backdrop-blur'
				: barState === 'restarting'
					? 'border-t border-orange-500/30 bg-orange-950/90 backdrop-blur'
					: 'border-t border-green-500/30 bg-green-950/90 backdrop-blur'}"
	>
		<div class="max-w-2xl mx-auto flex items-center justify-center gap-2 py-2.5 px-6">
			{#if barState === "restart-needed"}
				<span class="text-sm text-amber-300">Settings changed. Restart engine?</span>
				<button
					class="ml-2 inline-flex items-center gap-1.5 rounded-md bg-amber-600 hover:bg-amber-500 px-3 py-1 text-xs font-medium text-white transition-colors"
					onclick={handleRestart}
				>
					<RotateCcw class="size-3" />
					Restart
				</button>
			{:else if barState === "restarting"}
				<Loader class="size-3.5 animate-spin text-orange-400" />
				<span class="text-sm text-orange-300">Engine restarting...</span>
			{:else}
				<CheckCircle class="size-3.5 text-green-400" />
				<span class="text-sm text-green-300">Engine ready</span>
			{/if}
		</div>
	</div>
{/if}
