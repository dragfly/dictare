<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import { Loader, CheckCircle, RotateCcw } from "lucide-svelte";
	import * as settingsStore from "$lib/stores/settings.svelte";
	import { restartEngine, pingEngine } from "$lib/api";

	type BarState = "hidden" | "restart-needed" | "restarting" | "disconnected" | "ready";

	let barState = $state<BarState>("hidden");
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
		// Poll until engine is healthy again
		while (true) {
			await new Promise<void>((r) => setTimeout(r, 1000));
			if (await checkEngine()) break;
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

		if (!up && barState !== "restarting") {
			// Engine is down and we're not already waiting for a restart
			barState = "disconnected";
			if (hideTimer) {
				clearTimeout(hideTimer);
				hideTimer = null;
			}
		} else if (up && (barState === "disconnected" || barState === "restarting")) {
			// Engine is back
			settingsStore.clearNeedsRestart();
			barState = "ready";
			hideTimer = setTimeout(() => {
				barState = "hidden";
				hideTimer = null;
			}, 1500);
		}
	}

	onMount(() => {
		timer = setInterval(poll, 2000);
	});

	onDestroy(() => {
		if (timer) clearInterval(timer);
		if (hideTimer) clearTimeout(hideTimer);
	});
</script>

{#if barState !== "hidden"}
	<div
		class="fixed bottom-0 left-0 right-0 z-50 transition-all duration-300 border-t backdrop-blur
			{barState === 'restart-needed'
				? 'border-amber-500/30 bg-amber-950/90'
				: barState === 'restarting'
					? 'border-orange-500/30 bg-orange-950/90'
					: barState === 'disconnected'
						? 'border-red-500/30 bg-red-950/90'
						: 'border-green-500/30 bg-green-950/90'}"
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
			{:else if barState === "disconnected"}
				<Loader class="size-3.5 animate-spin text-red-400" />
				<span class="text-sm text-red-300">Engine disconnected</span>
			{:else}
				<CheckCircle class="size-3.5 text-green-400" />
				<span class="text-sm text-green-300">Engine ready</span>
			{/if}
		</div>
	</div>
{/if}
