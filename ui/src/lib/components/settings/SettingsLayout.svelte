<script lang="ts">
	import SettingsNav from "./SettingsNav.svelte";
	import SettingsSection from "./SettingsSection.svelte";
	import SaveBar from "./SaveBar.svelte";
	import EngineStatusBar from "./EngineStatusBar.svelte";
	import DashboardPage from "$lib/components/dashboard/DashboardPage.svelte";
	import ModelsPage from "$lib/components/models/ModelsPage.svelte";
	import { Button } from "$lib/components/ui/button";
	import { RotateCcw } from "lucide-svelte";
	import type { TabDef, NavChild } from "$lib/types";
	import * as settingsStore from "$lib/stores/settings.svelte";
	import { getFixedBottomPx } from "$lib/stores/settings.svelte";
	import { restartEngine, pingEngine, getSystemInfo, setLaunchAtLogin } from "$lib/api";
	import { onMount } from "svelte";

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

	onMount(() => {
		settingsStore.load();
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
				<DashboardPage />
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
				{#if activeNavId === "advanced-daemon"}
					<div class="px-4 mb-6 space-y-3">
						{#if launchAtLogin !== null}
							<div class="flex items-center justify-between rounded-lg border px-4 py-3">
								<div>
									<div class="text-sm font-medium">Launch at login</div>
									<div class="text-xs text-muted-foreground">Start engine and tray automatically at login</div>
								</div>
								<button
									role="switch"
									aria-checked={launchAtLogin}
									onclick={toggleLaunchAtLogin}
									class="relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring {launchAtLogin ? 'bg-primary' : 'bg-input'}"
								>
									<span class="pointer-events-none block h-4 w-4 rounded-full bg-background shadow-lg ring-0 transition-transform {launchAtLogin ? 'translate-x-4' : 'translate-x-0'}"></span>
								</button>
							</div>
						{/if}
						<div>
							<Button variant="destructive" onclick={handleRestart} disabled={restarting}>
								<RotateCcw class="size-3.5 mr-1.5 {restarting ? 'animate-spin' : ''}" />
								{restarting ? "Restarting…" : "Restart Engine"}
							</Button>
						</div>
					</div>
				{/if}
				<SettingsSection sections={activeSections} isGeneral={activeNavId === "advanced-general"} {schema} />
			{:else}
				<div class="text-muted-foreground py-20 text-center text-sm">Loading settings...</div>
			{/if}
			<SaveBar />
		</div>
	</main>
	<EngineStatusBar />
</div>
