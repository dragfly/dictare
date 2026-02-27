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

	type ProgressSnapshot = {
		status: string;
		fraction: number;
		message?: string;
	};
	let progress = $state<Record<string, ProgressSnapshot>>({});
	let installing = $state<Record<string, boolean>>({});
	let installErrors = $state<Record<string, string>>({});

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

	function handleRowClick(cap: CapabilityInfo) {
		const isInstalling = !!progress[cap.id] || cap.downloading;
		if (!cap.ready || isInstalling || saving || cap.configured) return;
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
			settingsStore.setNeedsRestart();
			await load();
		} catch (e) {
			installErrors = { ...installErrors, [pendingSelection.id]: String(e) };
		} finally {
			saving = false;
		}
	}

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
					{@const clickable = cap.ready && !isInstalling && !saving && !cap.configured}
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
								{#if cap.ready && !cap.builtin && cap.venv_installed && !cap.configured && !isInstalling}
									<Button
										variant="ghost"
										size="sm"
										class="text-muted-foreground hover:text-destructive px-2 h-7"
										onclick={(e: MouseEvent) => { e.stopPropagation(); handleUninstall(cap.id); }}
										title="Remove isolated environment"
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
