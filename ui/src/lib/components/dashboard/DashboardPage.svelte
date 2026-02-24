<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import { fetchStatus, type StatusResponse, type EngineInfo } from "$lib/api";
	import { Badge } from "$lib/components/ui/badge";
	import { Button } from "$lib/components/ui/button";
	import {
		CheckCircle,
		XCircle,
		AlertCircle,
		Loader,
		Copy,
		Check,
	} from "lucide-svelte";

	let status = $state<StatusResponse | null>(null);
	let loading = $state(true);
	let loadError = $state<string | null>(null);
	let copiedHint = $state<string | null>(null);

	let es: EventSource | null = null;
	let refreshTimer: ReturnType<typeof setInterval> | null = null;

	async function load() {
		loading = true;
		loadError = null;
		try {
			status = await fetchStatus();
		} catch (e) {
			loadError = String(e);
		} finally {
			loading = false;
		}
	}

	function connectSSE() {
		es = new EventSource("/status/stream");
		es.onmessage = (evt) => {
			try {
				status = JSON.parse(evt.data) as StatusResponse;
			} catch {
				// ignore malformed events
			}
		};
		es.onerror = () => {
			// SSE disconnected — fall back to polling
			es?.close();
			es = null;
			if (!refreshTimer) {
				refreshTimer = setInterval(load, 5000);
			}
		};
	}

	async function copyHint(hint: string) {
		await navigator.clipboard.writeText(hint);
		copiedHint = hint;
		setTimeout(() => {
			copiedHint = null;
		}, 2000);
	}

	function fmtUptime(seconds: number): string {
		seconds = Math.floor(seconds);
		if (seconds < 60) return `${seconds}s`;
		const minutes = Math.floor(seconds / 60);
		if (minutes < 60) return `${minutes}m`;
		const hours = Math.floor(minutes / 60);
		const rem = minutes % 60;
		return `${hours}h ${rem}m`;
	}

	onMount(() => {
		load();
		connectSSE();
	});

	onDestroy(() => {
		es?.close();
		if (refreshTimer) clearInterval(refreshTimer);
	});

	const p = $derived(status?.platform);
</script>

{#if loading && !status}
	<div class="text-muted-foreground py-20 text-center text-sm">Loading status...</div>
{:else if loadError && !status}
	<div class="flex flex-col items-center gap-3 py-20">
		<AlertCircle class="size-6 text-destructive" />
		<p class="text-sm text-destructive">{loadError}</p>
		<Button variant="outline" size="sm" onclick={load}>Retry</Button>
	</div>
{:else if p}
	<div class="space-y-6 px-4">
		<!-- Engine overview card -->
		<div class="rounded-lg border bg-card p-4 space-y-2">
			<div class="flex items-center justify-between">
				<h3 class="text-sm font-semibold">Engine</h3>
				<Badge variant="outline" class="text-[10px]">{p.mode} mode</Badge>
			</div>
			<div class="grid grid-cols-2 gap-x-8 gap-y-1 text-sm">
				<div class="text-muted-foreground">State</div>
				<div>{p.state}</div>
				<div class="text-muted-foreground">Uptime</div>
				<div>{fmtUptime(p.uptime_seconds)}</div>
				<div class="text-muted-foreground">STT</div>
				<div>{p.stt.model_name} <span class="text-muted-foreground">on {p.stt.device}</span></div>
				<div class="text-muted-foreground">TTS</div>
				<div>
					{p.tts.engine}
					{#if p.tts.available}
						<span class="text-green-500 text-xs ml-1">active</span>
					{:else}
						<span class="text-destructive text-xs ml-1">unavailable</span>
					{/if}
				</div>
			</div>
		</div>

		<!-- Agents card -->
		<div class="rounded-lg border bg-card p-4 space-y-2">
			<h3 class="text-sm font-semibold">Agents</h3>
			{#if p.output.available_agents.length > 0}
				<div class="flex flex-wrap gap-2">
					{#each p.output.available_agents as agent}
						<Badge
							variant={agent === p.output.current_agent ? "default" : "secondary"}
							class="text-xs"
						>
							{agent}
							{#if agent === p.output.current_agent}
								<span class="ml-1 opacity-70">active</span>
							{/if}
						</Badge>
					{/each}
				</div>
			{:else}
				<p class="text-sm text-muted-foreground">No agents connected</p>
			{/if}
		</div>

		<!-- TTS Engines -->
		{#if p.engines?.tts}
			<div class="rounded-lg border bg-card p-4 space-y-3">
				<h3 class="text-sm font-semibold">TTS Engines</h3>
				<div class="space-y-2">
					{#each p.engines.tts as eng (eng.name)}
						{@render engineRow(eng)}
					{/each}
				</div>
			</div>
		{/if}

		<!-- STT Engines -->
		{#if p.engines?.stt}
			<div class="rounded-lg border bg-card p-4 space-y-3">
				<h3 class="text-sm font-semibold">STT Engines</h3>
				<div class="space-y-2">
					{#each p.engines.stt as eng (eng.name)}
						{@render engineRow(eng)}
					{/each}
				</div>
			</div>
		{/if}

		<!-- Permissions -->
		{#if p.permissions}
			<div class="rounded-lg border bg-card p-4 space-y-2">
				<h3 class="text-sm font-semibold">Permissions</h3>
				<div class="flex flex-wrap gap-3">
					{#each Object.entries(p.permissions) as [key, ok]}
						<div class="flex items-center gap-1.5 text-sm">
							{#if ok}
								<CheckCircle class="size-3.5 text-green-500" />
							{:else}
								<XCircle class="size-3.5 text-destructive" />
							{/if}
							<span class="capitalize">{key.replace("_", " ")}</span>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	</div>
{/if}

{#snippet engineRow(eng: EngineInfo)}
	<div class="flex items-start justify-between gap-4 py-1">
		<div class="flex items-center gap-2 min-w-0 flex-1">
			{#if eng.available}
				<CheckCircle class="size-3.5 text-green-500 shrink-0" />
			{:else if !eng.platform_ok}
				<AlertCircle class="size-3.5 text-muted-foreground shrink-0" />
			{:else}
				<XCircle class="size-3.5 text-destructive shrink-0" />
			{/if}
			<div class="min-w-0">
				<div class="flex items-center gap-1.5">
					<span class="text-sm font-medium">{eng.name}</span>
					{#if eng.configured}
						<Badge class="text-[10px] px-1.5 py-0">in use</Badge>
					{/if}
				</div>
				<p class="text-xs text-muted-foreground">{eng.description}</p>
			</div>
		</div>
		{#if !eng.available && eng.install_hint}
			<button
				class="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors shrink-0 font-mono bg-muted/50 rounded px-2 py-1"
				onclick={() => copyHint(eng.install_hint)}
				title="Copy install command"
			>
				{#if copiedHint === eng.install_hint}
					<Check class="size-3 text-green-500" />
				{:else}
					<Copy class="size-3" />
				{/if}
				<span class="max-w-[200px] truncate">{eng.install_hint}</span>
			</button>
		{/if}
	</div>
{/snippet}
