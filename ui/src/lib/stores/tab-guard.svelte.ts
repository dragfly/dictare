/**
 * Tab takeover via BroadcastChannel.
 *
 * The most recently opened tab is always the "active" one.
 * On init it broadcasts "takeover", which tells all other tabs
 * to show a disconnected state and tear down their SSE connections.
 */

let evicted = $state(false);

const CHANNEL_NAME = "dictare-ui";

let channel: BroadcastChannel | null = null;

export function initTabGuard(): void {
	if (channel) return;

	channel = new BroadcastChannel(CHANNEL_NAME);

	channel.onmessage = (event: MessageEvent) => {
		if (event.data?.type === "takeover") {
			evicted = true;
		}
	};

	// This tab takes over — tell all others to step down
	channel.postMessage({ type: "takeover" });
}

export function isEvicted(): boolean {
	return evicted;
}
