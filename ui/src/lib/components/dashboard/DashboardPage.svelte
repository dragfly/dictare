<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import { fetchStatus, setOutputMode, type StatusResponse } from "$lib/api";
	import { Badge } from "$lib/components/ui/badge";
	import { Button } from "$lib/components/ui/button";
	import { CheckCircle, XCircle, AlertCircle } from "lucide-svelte";

	let status = $state<StatusResponse | null>(null);
	let loading = $state(true);
	let loadError = $state<string | null>(null);

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
	const outputMode = $derived(p?.output.mode ?? "agents");

	async function switchMode(mode: "keyboard" | "agents") {
		if (mode === outputMode) return;
		await setOutputMode(mode);
	}
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
	<div class="space-y-4 px-4">
		<!-- Engine (left) + Permissions (right) -->
		<div class="grid grid-cols-2 gap-4">
			<!-- Engine -->
			<div class="rounded-lg border bg-card p-4 space-y-2">
				<div class="flex items-center justify-between">
					<h3 class="text-sm font-semibold">Engine</h3>
					<Badge variant="outline" class="text-[10px]">{p.mode} mode</Badge>
				</div>
				<div class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
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
				<!-- Output mode toggle -->
				<div class="flex items-center gap-2 mt-3 pt-3 border-t border-border/50">
					<button
						onclick={() => switchMode("keyboard")}
						class="flex-1 py-1.5 text-xs rounded-md transition-colors
							{outputMode === 'keyboard'
								? 'bg-primary text-primary-foreground font-medium'
								: 'bg-muted text-muted-foreground hover:text-foreground'}"
					>
						Keyboard
					</button>
					<button
						onclick={() => switchMode("agents")}
						class="flex-1 py-1.5 text-xs rounded-md transition-colors
							{outputMode === 'agents'
								? 'bg-primary text-primary-foreground font-medium'
								: 'bg-muted text-muted-foreground hover:text-foreground'}"
					>
						Agents
					</button>
				</div>
			</div>

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

		<!-- Agents (full width below) -->
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
	</div>
{/if}
