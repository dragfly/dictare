<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import { Loader, CheckCircle } from "lucide-svelte";

	type BarState = "hidden" | "restarting" | "ready";

	let barState = $state<BarState>("hidden");
	let wasDown = false;
	let timer: ReturnType<typeof setInterval> | null = null;
	let hideTimer: ReturnType<typeof setTimeout> | null = null;

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
			barState = "ready";
			hideTimer = setTimeout(() => {
				barState = "hidden";
				hideTimer = null;
			}, 1500);
		}
		// If up and was never down, stay hidden
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
			{barState === 'restarting'
				? 'border-t border-orange-500/30 bg-orange-950/90 backdrop-blur'
				: 'border-t border-green-500/30 bg-green-950/90 backdrop-blur'}"
	>
		<div class="max-w-2xl mx-auto flex items-center justify-center gap-2 py-2.5 px-6">
			{#if barState === "restarting"}
				<Loader class="size-3.5 animate-spin text-orange-400" />
				<span class="text-sm text-orange-300">Engine restarting...</span>
			{:else}
				<CheckCircle class="size-3.5 text-green-400" />
				<span class="text-sm text-green-300">Engine ready</span>
			{/if}
		</div>
	</div>
{/if}
