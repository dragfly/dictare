<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import { fetchModels, pullModel, createPullProgressSource, type ModelInfo } from "$lib/api";
	import { Button } from "$lib/components/ui/button";
	import { Badge } from "$lib/components/ui/badge";
	import { Download, CheckCircle, AlertCircle, Loader } from "lucide-svelte";

	// Model list from backend
	let models = $state<ModelInfo[]>([]);
	let loading = $state(true);
	let loadError = $state<string | null>(null);

	// Live download progress from SSE: model_id → progress snapshot
	type ProgressSnapshot = {
		status: string;
		fraction: number;
		downloaded_bytes: number;
		total_bytes: number;
		message?: string;
	};
	let progress = $state<Record<string, ProgressSnapshot>>({});

	// Per-model pull-button state
	let pulling = $state<Record<string, boolean>>({});
	let pullErrors = $state<Record<string, string>>({});

	let es: EventSource | null = null;

	async function load() {
		loading = true;
		loadError = null;
		try {
			models = await fetchModels();
		} catch (e) {
			loadError = String(e);
		} finally {
			loading = false;
		}
	}

	function connectSSE() {
		es = createPullProgressSource();
		es.onmessage = (evt) => {
			const ev = JSON.parse(evt.data) as { model_id: string } & ProgressSnapshot;
			const { model_id, ...snap } = ev;

			if (snap.status === "done" || snap.status === "error") {
				// Remove from progress and refresh the model list
				const { [model_id]: _removed, ...rest } = progress;
				progress = rest;
				pulling = { ...pulling, [model_id]: false };
				load();
			} else {
				progress = { ...progress, [model_id]: snap };
			}
		};
	}

	async function handlePull(modelId: string) {
		pulling = { ...pulling, [modelId]: true };
		pullErrors = { ...pullErrors, [modelId]: "" };
		try {
			await pullModel(modelId);
			// Optimistic: show spinner immediately (SSE will take over)
			progress = {
				...progress,
				[modelId]: { status: "downloading", fraction: 0, downloaded_bytes: 0, total_bytes: 0 },
			};
		} catch (e) {
			pullErrors = { ...pullErrors, [modelId]: String(e) };
			pulling = { ...pulling, [modelId]: false };
		}
	}

	onMount(() => {
		load();
		connectSSE();
	});

	onDestroy(() => {
		es?.close();
	});

	const sttModels = $derived(models.filter((m) => m.type === "stt"));
	const ttsModels = $derived(models.filter((m) => m.type === "tts"));

	function fmtBytes(bytes: number): string {
		if (!bytes) return "—";
		if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
		return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
	}

	function fmtGb(gb: number): string {
		return gb < 1 ? `${(gb * 1024).toFixed(0)} MB` : `${gb.toFixed(2)} GB`;
	}
</script>

{#if loading}
	<div class="text-muted-foreground py-20 text-center text-sm">Loading models…</div>
{:else if loadError}
	<div class="flex flex-col items-center gap-3 py-20">
		<AlertCircle class="size-6 text-destructive" />
		<p class="text-sm text-destructive">{loadError}</p>
		<Button variant="outline" size="sm" onclick={load}>Retry</Button>
	</div>
{:else}
	<div class="space-y-8 px-4">
		{#each [["STT — Speech to Text", sttModels] as const, ["TTS — Text to Speech", ttsModels] as const] as [label, group]}
			{#if group.length > 0}
				<section>
					<h3 class="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
						{label}
					</h3>
					<div class="space-y-2">
						{#each group as model (model.id)}
							{@const snap = progress[model.id]}
							{@const isDownloading = !!snap || model.downloading}
							{@const pct = snap ? Math.round(snap.fraction * 100) : 0}

							<div class="rounded-lg border bg-card px-4 py-3">
								<!-- Header row -->
								<div class="flex items-start justify-between gap-4">
									<div class="flex-1 min-w-0">
										<div class="flex items-center gap-2 flex-wrap">
											<span class="font-medium text-sm">{model.id}</span>
											{#if model.configured}
												<Badge class="text-[10px] px-1.5 py-0">in use</Badge>
											{/if}
											{#if model.cached && !isDownloading}
												<span class="flex items-center gap-1 text-xs text-green-500">
													<CheckCircle class="size-3" /> Ready
												</span>
											{/if}
										</div>
										<p class="mt-0.5 text-xs text-muted-foreground">{model.description}</p>
										<p class="mt-0.5 text-[11px] text-muted-foreground/60">
											{model.cached ? fmtBytes(model.cache_size_bytes) : `~${fmtGb(model.size_gb)}`}
										</p>
									</div>

									<!-- Action button -->
									{#if isDownloading}
										<span class="flex items-center gap-1.5 text-xs text-blue-400 pt-0.5">
											<Loader class="size-3 animate-spin" />
											{pct}%
										</span>
									{:else if !model.cached}
										<Button
											size="sm"
											variant="outline"
											class="shrink-0"
											disabled={pulling[model.id]}
											onclick={() => handlePull(model.id)}
										>
											<Download class="mr-1.5 size-3.5" />
											Download
										</Button>
									{/if}
								</div>

								<!-- Progress bar -->
								{#if isDownloading}
									<div class="mt-3 space-y-1">
										<div class="h-1.5 w-full overflow-hidden rounded-full bg-muted">
											<div
												class="h-full rounded-full bg-blue-500 transition-all duration-500"
												style="width: {pct}%"
											></div>
										</div>
										{#if snap && snap.total_bytes > 0}
											<div class="flex justify-between text-[10px] text-muted-foreground/70">
												<span>{fmtBytes(snap.downloaded_bytes)}</span>
												<span>{fmtBytes(snap.total_bytes)}</span>
											</div>
										{/if}
									</div>
								{/if}

								<!-- Pull error -->
								{#if pullErrors[model.id]}
									<p class="mt-2 text-xs text-destructive">{pullErrors[model.id]}</p>
								{/if}
							</div>
						{/each}
					</div>
				</section>
			{/if}
		{/each}
	</div>
{/if}
