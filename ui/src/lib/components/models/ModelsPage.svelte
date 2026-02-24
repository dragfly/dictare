<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import {
		fetchCapabilities,
		installCapability,
		uninstallCapability,
		selectCapability,
		createPullProgressSource,
		type CapabilityInfo,
	} from "$lib/api";
	import * as settingsStore from "$lib/stores/settings.svelte";
	import { Button } from "$lib/components/ui/button";
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

	// Selection state: pending selection (before save)
	let pendingSelection = $state<{ type: "stt" | "tts"; id: string } | null>(null);
	let saving = $state(false);

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
		if (!confirm(`Uninstall ${capId}? The isolated environment will be removed.`)) return;
		try {
			await uninstallCapability(capId);
			await load();
		} catch {
			// ignore
		}
	}

	function handleRadioSelect(cap: CapabilityInfo) {
		if (!cap.ready || cap.configured) return;
		pendingSelection = { type: cap.type, id: cap.id };
	}

	function handleCancel() {
		pendingSelection = null;
	}

	async function handleSave() {
		if (!pendingSelection) return;
		saving = true;
		try {
			await selectCapability(pendingSelection.id);
			pendingSelection = null;
			// Signal that engine needs restart (footer bar will show prompt)
			settingsStore.setNeedsRestart();
			await load();
		} catch (e) {
			installErrors = { ...installErrors, [pendingSelection.id]: String(e) };
		} finally {
			saving = false;
		}
	}

	/** Is this capability effectively selected (configured or pending)? */
	function isSelected(cap: CapabilityInfo): boolean {
		if (pendingSelection && pendingSelection.type === cap.type) {
			return pendingSelection.id === cap.id;
		}
		return cap.configured;
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
	const maxRows = $derived(Math.max(sttCaps.length, ttsCaps.length));

	function fmtGb(gb: number): string {
		if (gb === 0) return "";
		return gb < 1 ? `~${(gb * 1024).toFixed(0)} MB` : `~${gb.toFixed(1)} GB`;
	}

	function platformLabel(cap: CapabilityInfo): string | null {
		if (!cap.platform_ok) {
			return "Unavailable on this platform";
		}
		if (cap.description.includes("Apple Silicon")) return "Apple Silicon";
		if (cap.description.includes("macOS")) return "macOS only";
		return null;
	}
</script>

{#snippet capCard(cap: CapabilityInfo)}
	{@const snap = progress[cap.id]}
	{@const isInstalling = !!snap || cap.downloading}
	{@const pct = snap ? Math.round(snap.fraction * 100) : 0}
	{@const platLabel = platformLabel(cap)}
	{@const selected = isSelected(cap)}
	{@const radioEnabled = cap.ready && !isInstalling && !saving}

	<button
		type="button"
		class="w-full h-full text-left rounded-lg border-2 bg-card px-4 py-3 transition-colors
			{selected ? 'border-green-500/70' : 'border-transparent'}
			{!cap.platform_ok ? 'opacity-50' : ''}
			{radioEnabled && !selected ? 'hover:border-muted-foreground/30 cursor-pointer' : ''}
			{!radioEnabled ? 'cursor-default' : ''}"
		onclick={() => radioEnabled && handleRadioSelect(cap)}
		disabled={!cap.platform_ok}
	>
		<div class="flex items-start gap-3">
			<!-- Radio button -->
			<div class="pt-0.5 shrink-0">
				<div
					class="size-4 rounded-full border-2 flex items-center justify-center transition-colors
						{selected ? 'border-green-500' : radioEnabled ? 'border-muted-foreground/40' : 'border-muted-foreground/20'}"
				>
					{#if selected}
						<div class="size-2 rounded-full bg-green-500"></div>
					{/if}
				</div>
			</div>

			<!-- Content -->
			<div class="flex-1 min-w-0">
				<div class="flex items-center gap-2 flex-wrap">
					<span class="font-medium text-sm">{cap.id}</span>
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
			<div class="flex items-center gap-1 shrink-0 pt-0.5">
				{#if isInstalling}
					<span class="flex items-center gap-1.5 text-xs text-blue-400">
						<Loader class="size-3 animate-spin" />
						{pct}%
					</span>
				{:else if !cap.ready && !cap.builtin && cap.platform_ok}
					<Button
						variant="ghost"
						size="sm"
						class="text-muted-foreground hover:text-foreground px-2"
						disabled={installing[cap.id]}
						onclick={(e: MouseEvent) => { e.stopPropagation(); handleInstall(cap.id); }}
						title="Download"
					>
						<Download class="size-3.5" />
					</Button>
				{/if}
				{#if cap.ready && !cap.builtin && cap.venv_installed && !cap.configured && !isInstalling}
					<Button
						variant="ghost"
						size="sm"
						class="text-muted-foreground hover:text-destructive px-2"
						onclick={(e: MouseEvent) => { e.stopPropagation(); handleUninstall(cap.id); }}
						title="Remove isolated environment"
					>
						<Trash2 class="size-3" />
					</Button>
				{/if}
			</div>
		</div>

		<!-- Progress bar -->
		{#if isInstalling}
			<div class="mt-3 ml-7 space-y-1">
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

		<!-- Error with hover tooltip -->
		{#if installErrors[cap.id]}
			<div class="mt-2 ml-7 group relative">
				<p class="text-xs text-destructive flex items-center gap-1">
					<AlertCircle class="size-3 shrink-0" />
					<span>Download failed</span>
				</p>
				<div class="absolute left-0 bottom-full mb-1 hidden group-hover:block
					bg-popover text-popover-foreground border rounded-md px-3 py-2
					text-xs max-w-[300px] shadow-md z-10 whitespace-pre-wrap">
					{installErrors[cap.id]}
				</div>
			</div>
		{/if}
	</button>
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
	<div class="px-4">
		<!-- Column headers -->
		<div class="grid grid-cols-2 gap-x-6 mb-3">
			<h3 class="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
				STT — Speech to Text
			</h3>
			<h3 class="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
				TTS — Text to Speech
			</h3>
		</div>

		<!-- Aligned grid: each row has one STT + one TTS card at matching height -->
		<div class="grid grid-cols-2 gap-x-6 gap-y-2">
			{#each Array(maxRows) as _, i}
				{#if sttCaps[i]}
					{@render capCard(sttCaps[i])}
				{:else}
					<div></div>
				{/if}
				{#if ttsCaps[i]}
					{@render capCard(ttsCaps[i])}
				{:else}
					<div></div>
				{/if}
			{/each}
		</div>
	</div>

	<!-- Save bar -->
	{#if pendingSelection}
		<div class="fixed bottom-0 left-0 right-0 border-t bg-background/95 backdrop-blur px-6 py-3 z-50">
			<div class="max-w-2xl mx-auto flex items-center justify-between">
				<p class="text-sm text-muted-foreground">
					Switch {pendingSelection.type === "stt" ? "STT model" : "TTS engine"} to
					<span class="font-medium text-foreground">{pendingSelection.id}</span>?
				</p>
				<div class="flex items-center gap-2">
					<Button variant="outline" size="sm" onclick={handleCancel} disabled={saving}>
						Cancel
					</Button>
					<Button size="sm" onclick={handleSave} disabled={saving}>
						{#if saving}
							<Loader class="size-3 animate-spin mr-1.5" />
							Saving...
						{:else}
							Save
						{/if}
					</Button>
				</div>
			</div>
		</div>
	{/if}
{/if}
