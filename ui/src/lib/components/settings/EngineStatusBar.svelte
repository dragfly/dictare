<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import { Loader, CheckCircle } from "lucide-svelte";
	import * as settingsStore from "$lib/stores/settings.svelte";
	import { setEngineBarVisible } from "$lib/stores/settings.svelte";

	type BarState = "hidden" | "restarting" | "loading" | "disconnected" | "ready";

	let barState = $state<BarState>("hidden");
	let sawDown = false;
	let timer: ReturnType<typeof setInterval> | null = null;
	let hideTimer: ReturnType<typeof setTimeout> | null = null;

	$effect(() => {
		setEngineBarVisible(barState !== "hidden");
	});

	// When saveStatus becomes "saved", transition to restarting and reset to idle.
	$effect(() => {
		if (settingsStore.getSaveStatus() === "saved") {
			barState = "restarting";
			sawDown = false;
			settingsStore.setSaveStatus("idle");
		}
	});

	async function checkEngine(): Promise<"down" | "loading" | "ready"> {
		try {
			const r = await fetch("/openvip/status", { signal: AbortSignal.timeout(2000) });
			if (!r.ok) return "down";
			const data = await r.json();
			if (data.platform?.loading?.active) return "loading";
			return "ready";
		} catch {
			return "down";
		}
	}

	async function poll() {
		const status = await checkEngine();

		if (status === "down") {
			if (barState === "restarting") {
				// Good — engine went down as expected during restart
				sawDown = true;
			} else {
				barState = "disconnected";
			}
			if (hideTimer) {
				clearTimeout(hideTimer);
				hideTimer = null;
			}
		} else if (barState === "restarting" && !sawDown) {
			// Engine still up after restart command — wait for it to go down first
			return;
		} else if (status === "loading") {
			barState = "loading";
		} else {
			// Engine is ready
			if (barState !== "hidden" && barState !== "ready") {
				barState = "ready";
				sawDown = false;
				// Reload full schema from backend now that engine is ready
				settingsStore.load();
				hideTimer = setTimeout(() => {
					barState = "hidden";
					hideTimer = null;
				}, 1500);
			}
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
		class="fixed bottom-0 left-0 right-0 z-50 transition-all duration-300 border-t backdrop-blur"
		style="border-color: {barState === 'restarting'
				? 'rgb(249 115 22 / 0.3)'
				: barState === 'loading'
					? 'rgb(245 158 11 / 0.3)'
					: barState === 'disconnected'
						? 'rgb(239 68 68 / 0.3)'
						: 'rgb(109 92 230 / 0.3)'};
			background-color: {barState === 'restarting'
				? 'rgb(67 20 7 / 0.9)'
				: barState === 'loading'
					? 'rgb(69 26 3 / 0.9)'
					: barState === 'disconnected'
						? 'rgb(69 10 10 / 0.9)'
						: 'rgb(29 20 66 / 0.9)'};"
	>
		<div class="max-w-2xl mx-auto flex items-center justify-center gap-2 py-2.5 px-6">
			{#if barState === "restarting"}
				<Loader class="size-3.5 animate-spin text-orange-400" />
				<span class="text-sm text-orange-300">Engine restarting...</span>
			{:else if barState === "loading"}
				<Loader class="size-3.5 animate-spin text-amber-400" />
				<span class="text-sm text-amber-300">Engine loading...</span>
			{:else if barState === "disconnected"}
				<Loader class="size-3.5 animate-spin text-red-400" />
				<span class="text-sm text-red-300">Engine disconnected</span>
			{:else}
				<CheckCircle class="size-3.5" style="color: #6d5ce6" />
				<span class="text-sm" style="color: #a99bf0">Engine ready</span>
			{/if}
		</div>
	</div>
{/if}
