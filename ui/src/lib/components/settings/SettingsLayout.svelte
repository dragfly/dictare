<script lang="ts">
	import SettingsNav from "./SettingsNav.svelte";
	import SettingsSection from "./SettingsSection.svelte";
	import SaveBar from "./SaveBar.svelte";
	import EngineStatusBar from "./EngineStatusBar.svelte";
	import DashboardPage from "$lib/components/dashboard/DashboardPage.svelte";
	import ModelsPage from "$lib/components/models/ModelsPage.svelte";
	import { Button } from "$lib/components/ui/button";
	import { RotateCcw, CheckCircle, XCircle } from "lucide-svelte";
	import type { TabDef, NavChild } from "$lib/types";
	import * as settingsStore from "$lib/stores/settings.svelte";
	import { getFixedBottomPx } from "$lib/stores/settings.svelte";
	import {
		restartEngine,
		pingEngine,
		getSystemInfo,
		setLaunchAtLogin,
		getPermissionDoctorStatus,
		openPermissionSetting,
		probePermissionDoctor,
		type PermissionDoctorStatus,
		type PermissionProbeResult
	} from "$lib/api";
	import { onMount, onDestroy } from "svelte";
	import { updateDeviceLists } from "$lib/stores/settings.svelte";
	import type { StatusResponse } from "$lib/api";

	interface Props {
		tabs: TabDef[];
	}

	let { tabs }: Props = $props();

	// Default to the first leaf: if first tab has children, select first child
	function defaultNavId(): string {
		const first = tabs[0];
		if (!first) return "";
		return first.children ? first.children[0].id : first.id;
	}

	let activeNavId = $state(defaultNavId());

	// Global SSE listener for device list updates — stays active on ALL tabs.
	// DashboardPage has its own SSE for dashboard-specific status display.
	let deviceSSE: EventSource | null = null;

	function connectDeviceSSE() {
		deviceSSE = new EventSource("/openvip/status/stream");
		deviceSSE.onmessage = (evt) => {
			try {
				const parsed = JSON.parse(evt.data) as StatusResponse;
				updateDeviceLists(parsed);
			} catch {
				// ignore
			}
		};
		deviceSSE.onerror = () => {
			deviceSSE?.close();
			deviceSSE = null;
			// Retry after 5s
			setTimeout(connectDeviceSSE, 5000);
		};
	}

	onMount(() => {
		settingsStore.load();
		connectDeviceSSE();
	});

	onDestroy(() => {
		deviceSSE?.close();
	});

	const schema = $derived(settingsStore.getSchema());

	/**
	 * Resolve the active view from activeNavId.
	 * Returns { tab, child? } — child is set when a sub-item is active.
	 */
	const activeView = $derived((): { tab: TabDef; child?: NavChild } | null => {
		for (const tab of tabs) {
			if (tab.children) {
				const child = tab.children.find((c) => c.id === activeNavId);
				if (child) return { tab, child };
			} else if (tab.id === activeNavId) {
				return { tab };
			}
		}
		return null;
	});

	const activeSections = $derived(activeView()?.child?.sections ?? activeView()?.tab.sections ?? []);
	const activeLabel   = $derived(activeView()?.child?.label   ?? activeView()?.tab.label   ?? "");
	const activeDesc    = $derived(activeView()?.child?.desc    ?? activeView()?.tab.desc    ?? "");

	const fixedBottomPx = $derived(getFixedBottomPx());

	let restarting = $state(false);
	let launchAtLogin = $state<boolean | null>(null);
	let doctor = $state<PermissionDoctorStatus | null>(null);
	let probing = $state(false);
	let probeResult = $state<PermissionProbeResult | null>(null);

	onMount(async () => {
		try {
			const info = await getSystemInfo();
			launchAtLogin = info.launch_at_login;
		} catch {
			// non-macOS or engine not ready
		}
	});

	async function toggleLaunchAtLogin() {
		if (launchAtLogin === null) return;
		const next = !launchAtLogin;
		launchAtLogin = next;
		await setLaunchAtLogin(next);
	}

	async function refreshDoctor() {
		try {
			doctor = await getPermissionDoctorStatus();
		} catch {
			doctor = null;
		}
	}

	async function openDoctorSetting(target: "input_monitoring" | "accessibility" | "microphone") {
		await openPermissionSetting(target);
	}

	async function runDoctorProbe() {
		probing = true;
		probeResult = null;
		try {
			probeResult = await probePermissionDoctor(8);
		} finally {
			probing = false;
			await refreshDoctor();
		}
	}

	function runRecommendedFix() {
		const target = doctor?.diagnosis?.recommended_target ?? probeResult?.diagnosis?.recommended_target;
		if (target) {
			void openDoctorSetting(target);
		}
	}

	async function handleRestart() {
		restarting = true;
		await restartEngine();
		// Poll until engine is healthy again
		while (true) {
			await new Promise<void>((r) => setTimeout(r, 1000));
			const up = await pingEngine().catch(() => false);
			if (up) break;
		}
		restarting = false;
	}

	function openPermissionsDoctor() {
		activeNavId = "advanced-permissions";
	}

	$effect(() => {
		if (activeNavId === "advanced-permissions") {
			void refreshDoctor();
		}
	});

	$effect(() => {
		if (activeNavId !== "advanced-permissions") return;
		const timer = setInterval(() => {
			void refreshDoctor();
		}, 1000);
		return () => clearInterval(timer);
	});
</script>

<div class="flex h-screen">
	<SettingsNav {tabs} bind:activeNavId version={schema?.version ?? ""} />
	<main class="flex-1 overflow-y-auto" style="padding-bottom: {fixedBottomPx}px">
		<div class="max-w-2xl mx-auto pt-14 pb-8">
			{#if activeNavId === "dashboard"}
				<div class="px-4 mb-8">
					<h2 class="text-xl font-semibold mb-1.5">{activeLabel}</h2>
					<p class="text-sm text-muted-foreground">{activeDesc}</p>
				</div>
				<DashboardPage onOpenPermissionsDoctor={openPermissionsDoctor} />
			{:else if activeNavId === "models"}
				<div class="px-4 mb-8">
					<h2 class="text-xl font-semibold mb-1.5">{activeLabel}</h2>
					<p class="text-sm text-muted-foreground">{activeDesc}</p>
				</div>
				<ModelsPage />
			{:else if activeView() && schema}
				<div class="px-4 mb-8">
					<h2 class="text-xl font-semibold mb-1.5">{activeLabel}</h2>
					<p class="text-sm text-muted-foreground">{activeDesc}</p>
				</div>
			{#if activeNavId === "general"}
					{#if launchAtLogin !== null}
						<div class="px-4 mb-6">
							<div class="flex items-center justify-between rounded-lg border px-4 py-3">
								<div>
									<div class="text-sm font-medium">Launch at login</div>
									<div class="text-xs text-muted-foreground">Start engine and tray automatically at login</div>
								</div>
								<button
									role="switch"
									aria-checked={launchAtLogin}
									aria-label="Toggle launch at login"
									onclick={toggleLaunchAtLogin}
									class="relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring {launchAtLogin ? 'bg-primary' : 'bg-input'}"
								>
									<span class="pointer-events-none block h-4 w-4 rounded-full bg-background shadow-lg ring-0 transition-transform {launchAtLogin ? 'translate-x-4' : 'translate-x-0'}"></span>
								</button>
							</div>
						</div>
					{/if}
				{/if}
				{#if activeNavId === "advanced-permissions"}
					<div class="px-4 mb-6">
						<div class="rounded-lg border px-4 py-3 space-y-3">
							<div class="flex items-center justify-between">
								<div class="text-sm font-medium">Permission Doctor</div>
								<Button variant="outline" onclick={refreshDoctor}>Refresh</Button>
							</div>
							<p class="text-xs text-muted-foreground leading-relaxed">
								Speaking with AI should feel simple, but operating systems sometimes make keyboard and microphone permissions a bit capricious.
								This page is your guided checkpoint: it updates live, shows what is missing, and gives you the next concrete step to fix it.
							</p>
							{#if doctor && doctor.status === "ok"}
								<div class="rounded-md border px-3 py-2 {doctor.diagnosis?.code === 'ok' ? 'border-green-500/40 bg-green-500/5' : 'border-amber-500/40 bg-amber-500/5'}">
									<div class="text-xs font-medium {doctor.diagnosis?.code === 'ok' ? 'text-green-500' : 'text-amber-500'}">
										{doctor.diagnosis?.summary ?? "Diagnosis unavailable"}
									</div>
									{#if doctor.diagnosis?.steps && doctor.diagnosis.steps.length > 0}
										<ul class="mt-2 list-disc pl-5 text-xs text-muted-foreground space-y-1">
											{#each doctor.diagnosis.steps as step}
												<li>{step}</li>
											{/each}
										</ul>
									{/if}
								</div>
								<div class="rounded-md border px-3 py-2 text-xs space-y-1.5">
									<div class="flex items-center justify-between">
										<span class="text-muted-foreground">Accessibility</span>
										<span class="inline-flex items-center gap-1">
											{#if doctor.accessibility}
												<CheckCircle class="size-3.5 text-green-500" />
												<span>granted</span>
											{:else}
												<XCircle class="size-3.5 text-destructive" />
												<span>missing</span>
											{/if}
										</span>
									</div>
									<div class="flex items-center justify-between">
										<span class="text-muted-foreground">Microphone</span>
										<span class="inline-flex items-center gap-1">
											{#if doctor.microphone}
												<CheckCircle class="size-3.5 text-green-500" />
												<span>granted</span>
											{:else}
												<XCircle class="size-3.5 text-destructive" />
												<span>missing</span>
											{/if}
										</span>
									</div>
									<div class="flex items-center justify-between">
										<span class="text-muted-foreground">Input Monitoring</span>
										<span class="inline-flex items-center gap-1">
											{#if doctor.input_monitoring}
												<CheckCircle class="size-3.5 text-green-500" />
												<span>granted</span>
											{:else}
												<XCircle class="size-3.5 text-destructive" />
												<span>missing</span>
											{/if}
										</span>
									</div>
									<div class="flex items-center justify-between">
										<span class="text-muted-foreground">Hotkey capture</span>
										<span class="inline-flex items-center gap-1">
											{#if doctor.capture_healthy}
												<CheckCircle class="size-3.5 text-green-500" />
												<span>healthy</span>
											{:else}
												<XCircle class="size-3.5 text-destructive" />
												<span>not confirmed</span>
											{/if}
										</span>
									</div>
									<div class="flex items-center justify-between">
										<span class="text-muted-foreground">Provider</span>
										<span>{doctor.active_provider ?? "none"}</span>
									</div>
								</div>
								<div class="flex flex-wrap gap-2">
									<Button variant="outline" onclick={() => openDoctorSetting("input_monitoring")}>Open Input Monitoring</Button>
									<Button variant="outline" onclick={() => openDoctorSetting("accessibility")}>Open Accessibility</Button>
									<Button variant="outline" onclick={() => openDoctorSetting("microphone")}>Open Microphone</Button>
									{#if doctor.diagnosis?.recommended_target}
										<Button variant="destructive" onclick={runRecommendedFix}>Open Recommended Fix</Button>
									{/if}
								</div>
								<div class="flex items-center gap-2">
									<Button variant="destructive" onclick={handleRestart} disabled={restarting}>
										<RotateCcw class="size-3.5 mr-1.5 {restarting ? 'animate-spin' : ''}" />
										{restarting ? "Restarting…" : "Restart Dictare"}
									</Button>
									<Button onclick={runDoctorProbe} disabled={probing}>
										{probing ? "Waiting for Right ⌘…" : "Probe Hotkey (press Right ⌘)"}
									</Button>
								</div>
								{#if probeResult}
									<div class="rounded-md border px-3 py-2 {probeResult.ok ? 'border-green-500/40 bg-green-500/5' : 'border-red-500/40 bg-red-500/5'}">
										<div class="text-xs font-medium {probeResult.ok ? 'text-green-500' : 'text-red-500'}">
											{probeResult.message}
										</div>
										{#if probeResult.diagnosis?.steps && probeResult.diagnosis.steps.length > 0}
											<ul class="mt-2 list-disc pl-5 text-xs text-muted-foreground space-y-1">
												{#each probeResult.diagnosis.steps as step}
													<li>{step}</li>
												{/each}
											</ul>
										{/if}
									</div>
								{/if}
							{:else}
								<div class="text-xs text-muted-foreground">Doctor status unavailable.</div>
							{/if}
						</div>
					</div>
				{/if}
				<SettingsSection sections={activeSections} isGeneral={activeNavId === "advanced-general"} {schema} />
			{:else}
				<div class="text-muted-foreground py-20 text-center text-sm">Loading settings...</div>
			{/if}
		</div>
	</main>
	<SaveBar />
	<EngineStatusBar />
</div>
