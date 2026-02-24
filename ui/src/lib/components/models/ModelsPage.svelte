<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import {
		fetchCapabilities,
		installCapability,
		uninstallCapability,
		createPullProgressSource,
		type CapabilityInfo,
	} from "$lib/api";
	import { Button } from "$lib/components/ui/button";
	import { Badge } from "$lib/components/ui/badge";
	import { Download, CheckCircle, AlertCircle, Loader, Trash2 } from "lucide-svelte";

	let capabilities = $state<CapabilityInfo[]>([]);
	let loading = $state(true);
	let loadError = $state<string | null>(null);

	// Live progress from SSE: cap_id -> snapshot
	type ProgressSnapshot = {
		status: string;
		fraction: number;
		message?: string;
	};
	let progress = $state<Record<string, ProgressSnapshot>>({});

	// Per-capability install button state
	let installing = $state<Record<string, boolean>>({});
	let installErrors = $state<Record<string, string>>({});

	let es: EventSource | null = null;

	async function load() {
		loading = true;
		loadError = null;
		try {
			capabilities = await fetchCapabilities();
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
				const { [model_id]: _removed, ...rest } = progress;
				progress = rest;
				installing = { ...installing, [model_id]: false };
				if (snap.status === "error") {
					installErrors = { ...installErrors, [model_id]: snap.message || "Install failed" };
				}
				load();
			} else {
				progress = { ...progress, [model_id]: snap };
			}
		};
	}

	async function handleInstall(capId: string) {
		installing = { ...installing, [capId]: true };
		const { [capId]: _cleared, ...rest } = installErrors;
		installErrors = rest;
		try {
			const status = await installCapability(capId);
			if (status === "ready") {
				installing = { ...installing, [capId]: false };
				load();
				return;
			}
			progress = {
				...progress,
				[capId]: { status: "downloading", fraction: 0, message: "Starting..." },
			};
		} catch (e) {
			installErrors = { ...installErrors, [capId]: String(e) };
			installing = { ...installing, [capId]: false };
		}
	}

	async function handleUninstall(capId: string) {
		try {
			await uninstallCapability(capId);
			await load();
		} catch {
			// ignore
		}
	}

	onMount(() => {
		load();
		connectSSE();
	});

	onDestroy(() => {
		es?.close();
	});

	const sttCaps = $derived(capabilities.filter((c) => c.type === "stt"));
	const ttsCaps = $derived(capabilities.filter((c) => c.type === "tts"));

	function fmtGb(gb: number): string {
		if (gb === 0) return "";
		return gb < 1 ? `~${(gb * 1024).toFixed(0)} MB` : `~${gb.toFixed(1)} GB`;
	}

	function platformLabel(cap: CapabilityInfo): string | null {
		if (!cap.platform_ok) {
			return "Unavailable on this platform";
		}
		// Show platform hint based on description
		if (cap.description.includes("Apple Silicon")) return "Apple Silicon";
		if (cap.description.includes("macOS")) return "macOS only";
		return null;
	}
</script>

{#if loading}
	<div class="text-muted-foreground py-20 text-center text-sm">Loading capabilities...</div>
{:else if loadError}
	<div class="flex flex-col items-center gap-3 py-20">
		<AlertCircle class="size-6 text-destructive" />
		<p class="text-sm text-destructive">{loadError}</p>
		<Button variant="outline" size="sm" onclick={load}>Retry</Button>
	</div>
{:else}
	<div class="grid grid-cols-2 gap-6 px-4">
		{#each [["STT — Speech to Text", sttCaps] as const, ["TTS — Text to Speech", ttsCaps] as const] as [label, group]}
			<section>
				<h3 class="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
					{label}
				</h3>
				<div class="space-y-2">
					{#each group as cap (cap.id)}
						{@const snap = progress[cap.id]}
						{@const isInstalling = !!snap || cap.downloading}
						{@const pct = snap ? Math.round(snap.fraction * 100) : 0}
						{@const platLabel = platformLabel(cap)}

						<div class="rounded-lg border bg-card px-4 py-3" class:opacity-50={!cap.platform_ok}>
							<!-- Header row -->
							<div class="flex items-start justify-between gap-3">
								<div class="flex-1 min-w-0">
									<div class="flex items-center gap-2 flex-wrap">
										<span class="font-medium text-sm">{cap.id}</span>
										{#if cap.configured}
											<Badge class="text-[10px] px-1.5 py-0">in use</Badge>
										{/if}
										{#if cap.ready && !isInstalling}
											<span class="flex items-center gap-1 text-xs text-green-500">
												<CheckCircle class="size-3" /> Ready
											</span>
										{/if}
									</div>
									<p class="mt-0.5 text-xs text-muted-foreground">{cap.description}</p>
									<div class="mt-0.5 flex items-center gap-2">
										{#if fmtGb(cap.size_gb)}
											<span class="text-[11px] text-muted-foreground/60">{fmtGb(cap.size_gb)}</span>
										{/if}
										{#if platLabel}
											<span class="text-[11px] text-muted-foreground/60">{platLabel}</span>
										{/if}
									</div>
								</div>

								<!-- Action buttons -->
								<div class="flex items-center gap-1.5 shrink-0 pt-0.5">
									{#if isInstalling}
										<span class="flex items-center gap-1.5 text-xs text-blue-400">
											<Loader class="size-3 animate-spin" />
											{pct}%
										</span>
									{:else if !cap.ready && !cap.builtin && cap.platform_ok}
										<Button
											size="sm"
											variant="outline"
											disabled={installing[cap.id]}
											onclick={() => handleInstall(cap.id)}
										>
											<Download class="mr-1.5 size-3.5" />
											Download
										</Button>
									{/if}
									{#if cap.ready && !cap.builtin && cap.venv_installed && !isInstalling}
										<Button
											variant="ghost"
											size="sm"
											class="text-muted-foreground hover:text-destructive px-2"
											onclick={() => handleUninstall(cap.id)}
											title="Remove isolated environment"
										>
											<Trash2 class="size-3" />
										</Button>
									{/if}
								</div>
							</div>

							<!-- Progress bar -->
							{#if isInstalling}
								<div class="mt-3 space-y-1">
									<div class="h-1.5 w-full overflow-hidden rounded-full bg-muted">
										<div
											class="h-full rounded-full bg-blue-500 transition-all duration-500"
											style="width: {pct}%"
										></div>
									</div>
									{#if snap?.message}
										<p class="text-[10px] text-muted-foreground/70">{snap.message}</p>
									{/if}
								</div>
							{/if}

							<!-- Error -->
							{#if installErrors[cap.id]}
								<p class="mt-2 text-xs text-destructive">{installErrors[cap.id]}</p>
							{/if}
						</div>
					{/each}
				</div>
			</section>
		{/each}
	</div>
{/if}
