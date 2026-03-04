<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import { fetchStatus, setOutputMode, setCurrentAgent, type StatusResponse } from "$lib/api";
	import { updateDeviceLists } from "$lib/stores/settings.svelte";
	import { Button } from "$lib/components/ui/button";
	import { CheckCircle, XCircle, AlertCircle } from "lucide-svelte";

	interface Props {
		onOpenPermissionsDoctor?: () => void;
	}

	let { onOpenPermissionsDoctor }: Props = $props();

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
		es = new EventSource("/openvip/status/stream");
		es.onmessage = (evt) => {
			try {
				const parsed = JSON.parse(evt.data) as StatusResponse;
				status = parsed;
				updateDeviceLists(parsed);
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

	function fmtAudio(seconds: number): string {
		if (seconds < 60) return `${seconds.toFixed(0)}s`;
		return `${(seconds / 60).toFixed(1)}m`;
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

	async function handleAgentClick(agent: string) {
		if (!status || agent === p?.output.current_agent) return;
		// Optimistic update — instant UI response
		status = {
			...status,
			platform: {
				...status.platform,
				output: { ...status.platform.output, current_agent: agent },
			},
		};
		await setCurrentAgent(agent);
	}

	async function switchMode(mode: "keyboard" | "agents") {
		if (mode === outputMode) return;
		await setOutputMode(mode);
	}

	function goPermissionsDoctor() {
		onOpenPermissionsDoctor?.();
	}

	const sttHealthy = $derived(Boolean(p?.stt.model_name));
	const ttsHealthy = $derived(Boolean(p?.tts.available));
	const hotkeyState = $derived(p?.hotkey.status ?? "unknown");
	const hotkeyHealthy = $derived(hotkeyState === "confirmed" || hotkeyState === "bound");
	const hotkeyPending = $derived(hotkeyState === "active");
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
		<div class="grid grid-cols-[3fr_2fr] gap-4">
			<!-- Engine -->
			<div class="rounded-lg border bg-card p-4 space-y-2">
				<h3 class="text-sm font-semibold">Engine</h3>
				<div class="grid grid-cols-[auto_1fr_auto] gap-x-4 gap-y-1 text-sm">
					<div class="text-muted-foreground">STT</div>
					<div>{p.stt.model_name} <span class="text-muted-foreground">on {p.stt.device}</span></div>
					<div class="flex items-center justify-end">
						{#if sttHealthy}
							<CheckCircle class="size-4 text-green-500 shrink-0" />
						{:else}
							<AlertCircle class="size-4 text-yellow-500 shrink-0" />
						{/if}
					</div>
					<div class="text-muted-foreground">TTS</div>
					<div>
						{p.tts.engine}
						{#if !p.tts.available}
							<span class="text-destructive text-xs ml-1">error</span>
						{/if}
					</div>
					<div class="flex items-center justify-end">
						{#if ttsHealthy}
							<CheckCircle class="size-4 text-green-500 shrink-0" />
						{:else}
							<AlertCircle class="size-4 text-yellow-500 shrink-0" />
						{/if}
					</div>
					<div class="text-muted-foreground">Hotkey</div>
					<div>
						{p.hotkey.key}
						{#if hotkeyPending}
							<span class="text-yellow-500 text-xs ml-1" title="Tap created — press any key to confirm">confirming…</span>
						{:else if hotkeyState === "failed"}
							<span class="text-destructive text-xs ml-1">error</span>
						{:else if hotkeyState !== "confirmed" && hotkeyState !== "bound"}
							<span class="text-muted-foreground text-xs ml-1">{hotkeyState}</span>
						{/if}
					</div>
					<div class="flex items-center justify-end">
						{#if hotkeyHealthy}
							<CheckCircle class="size-4 text-green-500 shrink-0" />
						{:else if hotkeyPending}
							<AlertCircle class="size-4 text-yellow-500 shrink-0" />
						{:else}
							<button
								type="button"
								class="inline-flex items-center"
								title="Open Permissions Doctor"
								onclick={goPermissionsDoctor}
							>
								<XCircle class="size-4 text-destructive shrink-0 cursor-pointer" />
							</button>
						{/if}
					</div>
					<div class="text-muted-foreground">State</div>
					<div>{p.state}</div>
					<div></div>
					<div class="text-muted-foreground">Uptime</div>
					<div>{fmtUptime(p.uptime_seconds)}</div>
					<div></div>
					{#if p.stats && p.stats.transcriptions > 0}
					<div class="text-muted-foreground">Session</div>
					<div>{p.stats.transcriptions} tx · {p.stats.words} words · {fmtAudio(p.stats.audio_seconds)}</div>
					<div></div>
					{#if p.stats.phrase}
					<div></div>
					<div class="text-muted-foreground italic text-xs">{p.stats.phrase}</div>
					<div></div>
					{/if}
					{/if}
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
					<div class="flex flex-col gap-2">
						{#each Object.entries(p.permissions).filter(([k]) => !k.endsWith("_url")) as [key, ok]}
							<div class="flex items-center gap-1.5 text-sm">
								{#if ok}
									<CheckCircle class="size-3.5 text-green-500 shrink-0" />
									<span class="capitalize">{key.replace("_", " ")}</span>
								{:else}
									<button
										type="button"
										class="inline-flex items-center gap-1.5 hover:opacity-90"
										title="Open Permissions Doctor"
										onclick={goPermissionsDoctor}
									>
										<XCircle class="size-3.5 text-destructive shrink-0 cursor-pointer" />
										<span class="capitalize underline decoration-dotted underline-offset-2">{key.replace("_", " ")}</span>
									</button>
								{/if}
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
						<button
							onclick={() => handleAgentClick(agent)}
							class="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors
								{agent === p.output.current_agent
									? 'bg-primary text-primary-foreground border-transparent'
									: 'bg-secondary text-secondary-foreground border-transparent hover:bg-secondary/80'}"
						>
							{agent}
						</button>
					{/each}
				</div>
			{:else}
				<p class="text-sm text-muted-foreground">No agents connected</p>
			{/if}
		</div>
	</div>
{/if}
