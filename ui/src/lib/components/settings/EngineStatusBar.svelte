<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import { Loader, CheckCircle } from "lucide-svelte";
	import * as settingsStore from "$lib/stores/settings.svelte";
	import { setEngineBarVisible } from "$lib/stores/settings.svelte";

	type BarState = "hidden" | "restarting" | "disconnected" | "ready";

	let barState = $state<BarState>("hidden");
	let timer: ReturnType<typeof setInterval> | null = null;
	let hideTimer: ReturnType<typeof setTimeout> | null = null;

	$effect(() => {
		setEngineBarVisible(barState !== "hidden");
	});

	// When saveStatus becomes "saved", engine was already restarted by saveAll() —
	// show "restarting" and poll until healthy.
	$effect(() => {
		if (settingsStore.getSaveStatus() === "saved" && barState !== "restarting") {
			barState = "restarting";
		}
	});

	async function checkEngine(): Promise<boolean> {
		try {
			const r = await fetch("/health", { signal: AbortSignal.timeout(1000) });
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
			barState = "ready";
			hideTimer = setTimeout(() => {
				barState = "hidden";
				hideTimer = null;
			}, 1500);
		}
	}

	onMount(() => {
		timer = setInterval(poll, 1000);
	});

	onDestroy(() => {
		if (timer) clearInterval(timer);
		if (hideTimer) clearTimeout(hideTimer);
	});
</script>

{#if barState !== "hidden"}
	<div
		class="fixed bottom-0 left-0 right-0 z-50 transition-all duration-300 border-t backdrop-blur
			{barState === 'restarting'
				? 'border-orange-500/30 bg-orange-950/90'
				: barState === 'disconnected'
					? 'border-red-500/30 bg-red-950/90'
					: 'border-green-500/30 bg-green-950/90'}"
	>
		<div class="max-w-2xl mx-auto flex items-center justify-center gap-2 py-2.5 px-6">
			{#if barState === "restarting"}
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
