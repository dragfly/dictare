<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import {
		fetchCapabilities,
		installCapability,
		uninstallCapability,
		createPullProgressSource,
		type CapabilityInfo,
	} from "$lib/api";
	import * as settingsStore from "$lib/stores/settings.svelte";
	import { Button } from "$lib/components/ui/button";
	import { Download, CheckCircle, AlertCircle, Loader, Trash2 } from "lucide-svelte";

	let capabilities = $state<CapabilityInfo[]>([]);
	let loading = $state(true);
	let loadError = $state<string | null>(null);

	type ProgressSnapshot = {
		status: string;
		fraction: number;
		message?: string;
	};
	let progress = $state<Record<string, ProgressSnapshot>>({});
	let installing = $state<Record<string, boolean>>({});
	let installErrors = $state<Record<string, string>>({});

	let confirmUninstallId = $state<string | null>(null);

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

	function handleUninstall(capId: string) {
		confirmUninstallId = capId;
	}

	async function confirmUninstall() {
		const capId = confirmUninstallId;
		confirmUninstallId = null;
		if (!capId) return;
		try {
			await uninstallCapability(capId);
			await load();
		} catch {
			// ignore
		}
	}

	function handleRowClick(cap: CapabilityInfo) {
		const isInstalling = !!progress[cap.id] || cap.downloading;
		if (!cap.ready || isInstalling) return;

		const dirtyModels = settingsStore.getDirtyModels();
		const pendingForType = dirtyModels[cap.type];

		if (cap.configured && !pendingForType) {
			// Already active and no pending change — nothing to do
			return;
		}

		if (pendingForType === cap.id) {
			// Clicking the pending selection again — deselect it
			settingsStore.clearModelDirty(cap.type);
			return;
		}

		if (cap.configured) {
			// Clicking the currently configured model while another is pending — clear the pending
			settingsStore.clearModelDirty(cap.type);
			return;
		}

		settingsStore.markModelDirty(cap.type, cap.id);
	}

	function isSelected(cap: CapabilityInfo): boolean {
		const dirtyModels = settingsStore.getDirtyModels();
		if (cap.type in dirtyModels) {
			return dirtyModels[cap.type] === cap.id;
		}
		return cap.configured;
	}

	// Reload capabilities after successful save
	$effect(() => {
		if (settingsStore.getSaveStatus() === "saved") {
			load();
		}
	});

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
		if (gb === 0) return "—";
		return gb < 1 ? `~${(gb * 1024).toFixed(0)} MB` : `~${gb.toFixed(1)} GB`;
	}

	function platformBadge(cap: CapabilityInfo): string | null {
		if (!cap.platform_ok) {
			if (cap.description.includes("Apple Silicon")) return "Apple Silicon only";
			if (cap.description.includes("macOS")) return "macOS only";
			return "Unavailable";
		}
		return null;
	}
</script>

{#snippet capTable(caps: CapabilityInfo[], title: string)}
	<div class="rounded-lg border bg-card overflow-hidden">
		<div class="px-4 py-2.5 border-b bg-muted/30">
			<h3 class="text-xs font-semibold uppercase tracking-widest text-muted-foreground">{title}</h3>
		</div>
		<table class="w-full text-sm">
			<thead>
				<tr class="border-b text-xs text-muted-foreground">
					<th class="text-left font-medium px-4 py-2 w-6"></th>
					<th class="text-left font-medium px-3 py-2">Name</th>
					<th class="text-left font-medium px-3 py-2 hidden md:table-cell">Description</th>
					<th class="text-left font-medium px-3 py-2 w-24">Size</th>
					<th class="text-left font-medium px-3 py-2 w-36">Status</th>
					<th class="text-right font-medium px-4 py-2 w-20">Actions</th>
				</tr>
			</thead>
			<tbody>
				{#each caps as cap (cap.id)}
					{@const snap = progress[cap.id]}
					{@const isInstalling = !!snap || cap.downloading}
					{@const pct = snap ? Math.round(snap.fraction * 100) : 0}
					{@const selected = isSelected(cap)}
					{@const badge = platformBadge(cap)}
					{@const clickable = cap.ready && !isInstalling && !cap.configured}
					<tr
						class="border-b last:border-0 transition-colors
							{!cap.platform_ok ? 'opacity-40' : ''}
							{clickable ? 'cursor-pointer hover:bg-muted/40' : ''}
							{selected ? 'bg-green-950/20' : ''}"
						onclick={() => handleRowClick(cap)}
					>
						<!-- Radio -->
						<td class="px-4 py-3">
							<div
								class="size-3.5 rounded-full border-2 flex items-center justify-center shrink-0
									{selected ? 'border-green-500' : cap.ready ? 'border-muted-foreground/40' : 'border-muted-foreground/20'}"
							>
								{#if selected}
									<div class="size-1.5 rounded-full bg-green-500"></div>
								{/if}
							</div>
						</td>

						<!-- Name -->
						<td class="px-3 py-3 font-medium">{cap.id}</td>

						<!-- Description -->
						<td class="px-3 py-3 text-xs text-muted-foreground hidden md:table-cell">
							{cap.description}
						</td>

						<!-- Size -->
						<td class="px-3 py-3 text-xs text-muted-foreground">{fmtGb(cap.size_gb)}</td>

						<!-- Status -->
						<td class="px-3 py-3">
							{#if isInstalling}
								<div class="space-y-1">
									<div class="flex items-center gap-1.5 text-xs text-blue-400">
										<Loader class="size-3 animate-spin shrink-0" />
										<span>{pct}%</span>
									</div>
									<div class="h-1 w-24 overflow-hidden rounded-full bg-muted">
										<div
											class="h-full rounded-full bg-blue-500 transition-all duration-500"
											style="width: {pct}%"
										></div>
									</div>
									{#if snap?.message}
										<p class="text-[10px] text-muted-foreground/60 truncate max-w-[120px]">{snap.message}</p>
									{/if}
								</div>
							{:else if cap.ready}
								<span class="flex items-center gap-1 text-xs text-green-500">
									<CheckCircle class="size-3 shrink-0" /> Ready
								</span>
							{:else if badge}
								<span class="text-xs text-muted-foreground/60">{badge}</span>
							{:else if cap.platform_ok}
								<span class="text-xs text-muted-foreground/50">Not installed</span>
							{/if}
							{#if installErrors[cap.id]}
								<div class="group relative mt-1">
									<p class="text-xs text-destructive flex items-center gap-1">
										<AlertCircle class="size-3 shrink-0" />
										<span>Failed</span>
									</p>
									<div class="absolute left-0 bottom-full mb-1 hidden group-hover:block
										bg-popover text-popover-foreground border rounded-md px-3 py-2
										text-xs max-w-[280px] shadow-md z-10 whitespace-pre-wrap">
										{installErrors[cap.id]}
									</div>
								</div>
							{/if}
						</td>

						<!-- Actions -->
						<td class="px-4 py-3 text-right">
							<div class="flex items-center justify-end gap-1">
								{#if !isInstalling && !cap.ready && !cap.builtin && cap.platform_ok}
									<Button
										variant="ghost"
										size="sm"
										class="text-muted-foreground hover:text-foreground px-2 h-7"
										disabled={installing[cap.id]}
										onclick={(e: MouseEvent) => { e.stopPropagation(); handleInstall(cap.id); }}
										title="Download"
									>
										<Download class="size-3.5" />
									</Button>
								{/if}
								{#if !cap.builtin && (cap.venv_installed || cap.model_cached) && !cap.configured && !isInstalling}
									<Button
										variant="ghost"
										size="sm"
										class="text-muted-foreground hover:text-destructive px-2 h-7"
										onclick={(e: MouseEvent) => { e.stopPropagation(); handleUninstall(cap.id); }}
										title="Remove downloaded files"
									>
										<Trash2 class="size-3" />
									</Button>
								{/if}
							</div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/snippet}

{#if loading && capabilities.length === 0}
	<div class="text-muted-foreground py-20 text-center text-sm">Loading capabilities...</div>
{:else if loadError && capabilities.length === 0}
	<div class="flex flex-col items-center gap-3 py-20">
		<AlertCircle class="size-6 text-destructive" />
		<p class="text-sm text-destructive">{loadError}</p>
		<Button variant="outline" size="sm" onclick={load}>Retry</Button>
	</div>
{:else}
	<div class="px-4 space-y-4">
		{@render capTable(sttCaps, "STT — Speech to Text")}
		{@render capTable(ttsCaps, "TTS — Text to Speech")}
	</div>

	<!-- Uninstall confirm dialog -->
	{#if confirmUninstallId}
		<div
			class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
			onclick={() => confirmUninstallId = null}
			role="presentation"
		>
			<div
				class="bg-card border rounded-xl shadow-xl p-6 w-80 space-y-4"
				onclick={(e) => e.stopPropagation()}
				role="presentation"
			>
				<div class="space-y-1">
					<p class="text-sm font-semibold">Remove {confirmUninstallId}?</p>
					<p class="text-xs text-muted-foreground">Downloaded files will be deleted. You can reinstall at any time.</p>
				</div>
				<div class="flex gap-2 justify-end">
					<Button variant="outline" size="sm" onclick={() => confirmUninstallId = null}>Cancel</Button>
					<Button variant="destructive" size="sm" onclick={confirmUninstall}>Remove</Button>
				</div>
			</div>
		</div>
	{/if}
{/if}
