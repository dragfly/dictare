<script lang="ts">
	import { Button } from "$lib/components/ui/button";
	import { captureHotkey } from "$lib/api";

	interface Props {
		format: "evdev" | "shortcut";
		value: string;
		onchange: (v: string) => void;
	}

	let { format, value, onchange }: Props = $props();

	let capturing = $state(false);
	let abortController: AbortController | null = null;

	// ---------------------------------------------------------------------------
	// evdev: browser KeyboardEvent.code → KEY_* (kernel evdev names)
	// ---------------------------------------------------------------------------

	const EVDEV_MAP: Record<string, string> = {
		MetaRight: "KEY_RIGHTMETA",    MetaLeft: "KEY_LEFTMETA",
		ScrollLock: "KEY_SCROLLLOCK",  CapsLock: "KEY_CAPSLOCK",
		NumLock: "KEY_NUMLOCK",        Pause: "KEY_PAUSE",
		PrintScreen: "KEY_SYSRQ",      Escape: "KEY_ESC",
		Enter: "KEY_ENTER",            Tab: "KEY_TAB",
		Backspace: "KEY_BACKSPACE",    Space: "KEY_SPACE",
		Insert: "KEY_INSERT",          Delete: "KEY_DELETE",
		Home: "KEY_HOME",              End: "KEY_END",
		PageUp: "KEY_PAGEUP",          PageDown: "KEY_PAGEDOWN",
		ArrowUp: "KEY_UP",             ArrowDown: "KEY_DOWN",
		ArrowLeft: "KEY_LEFT",         ArrowRight: "KEY_RIGHT",
		ShiftLeft: "KEY_LEFTSHIFT",    ShiftRight: "KEY_RIGHTSHIFT",
		ControlLeft: "KEY_LEFTCTRL",   ControlRight: "KEY_RIGHTCTRL",
		AltLeft: "KEY_LEFTALT",        AltRight: "KEY_RIGHTALT",
		AudioVolumeMute: "KEY_MUTE",   AudioVolumeUp: "KEY_VOLUMEUP",
		AudioVolumeDown: "KEY_VOLUMEDOWN",
	};

	function codeToEvdev(code: string): string {
		if (EVDEV_MAP[code]) return EVDEV_MAP[code];
		if (/^F\d+$/.test(code)) return "KEY_" + code;                  // F1-F24
		if (code.startsWith("Key")) return "KEY_" + code.slice(3);       // KeyA → KEY_A
		if (code.startsWith("Digit")) return "KEY_" + code.slice(5);     // Digit1 → KEY_1
		if (code.startsWith("Numpad")) {
			const rest = code.slice(6);
			return /^\d+$/.test(rest) ? "KEY_KP" + rest : "KEY_KP" + rest.toUpperCase();
		}
		return "KEY_" + code.toUpperCase();
	}

	// ---------------------------------------------------------------------------
	// shortcut: KeyboardEvent → pynput-style string (e.g. "shift+enter")
	// ---------------------------------------------------------------------------

	const SHORTCUT_KEY_MAP: Record<string, string> = {
		Enter: "enter",     Escape: "esc",      Tab: "tab",
		Backspace: "backspace", Delete: "delete", Space: "space",
		" ": "space",
		Home: "home",       End: "end",
		PageUp: "page_up",  PageDown: "page_down",
		ArrowUp: "up",      ArrowDown: "down",
		ArrowLeft: "left",  ArrowRight: "right",
		Insert: "insert",
	};

	function eventToShortcut(e: KeyboardEvent): string {
		const modifiers: string[] = [];
		if (e.ctrlKey) modifiers.push("ctrl");
		if (e.altKey) modifiers.push("alt");
		if (e.shiftKey) modifiers.push("shift");
		if (e.metaKey) modifiers.push("cmd");

		const raw = e.key;
		if (["Control", "Alt", "Shift", "Meta"].includes(raw)) return ""; // pure modifier
		const main = SHORTCUT_KEY_MAP[raw] ?? (/^F\d+$/.test(raw) ? raw.toLowerCase() : raw.toLowerCase());
		return [...modifiers, main].join("+");
	}

	// ---------------------------------------------------------------------------
	// Human-friendly display
	// ---------------------------------------------------------------------------

	const EVDEV_HUMAN: Record<string, string> = {
		KEY_RIGHTMETA: "Right ⌘",   KEY_LEFTMETA: "Left ⌘",
		KEY_SCROLLLOCK: "Scroll Lock", KEY_CAPSLOCK: "Caps Lock",
		KEY_NUMLOCK: "Num Lock",    KEY_PAUSE: "Pause",
		KEY_SYSRQ: "Print Screen",  KEY_ESC: "Esc",
		KEY_ENTER: "Return",        KEY_TAB: "Tab",
		KEY_BACKSPACE: "⌫",         KEY_SPACE: "Space",
		KEY_INSERT: "Ins",          KEY_DELETE: "Del",
		KEY_HOME: "Home",           KEY_END: "End",
		KEY_PAGEUP: "PgUp",         KEY_PAGEDOWN: "PgDn",
		KEY_UP: "↑",                KEY_DOWN: "↓",
		KEY_LEFT: "←",              KEY_RIGHT: "→",
		KEY_MUTE: "Mute",           KEY_VOLUMEUP: "Vol+",
		KEY_VOLUMEDOWN: "Vol−",
	};

	const SHORTCUT_PART_HUMAN: Record<string, string> = {
		ctrl: "⌃", alt: "⌥", shift: "⇧", cmd: "⌘",
		enter: "Return", esc: "Esc", tab: "Tab",
		backspace: "⌫", delete: "Del", space: "Space",
		up: "↑", down: "↓", left: "←", right: "→",
		page_up: "PgUp", page_down: "PgDn",
		home: "Home", end: "End", insert: "Ins",
	};

	function humanLabel(v: string): string {
		if (!v) return "";
		if (format === "evdev") {
			if (EVDEV_HUMAN[v]) return EVDEV_HUMAN[v];
			if (/^KEY_F\d+$/.test(v)) return v.slice(4);    // KEY_F12 → F12
			if (/^KEY_[A-Z\d]$/.test(v)) return v.slice(4); // KEY_A → A
			return v;
		}
		// shortcut format: "shift+enter" → "⇧ Return"
		return v.split("+").map(p => SHORTCUT_PART_HUMAN[p] ?? p.toUpperCase()).join(" ");
	}

	const display = $derived(humanLabel(value));

	// ---------------------------------------------------------------------------
	// Key capture logic
	// ---------------------------------------------------------------------------

	const MODIFIER_KEYS = new Set(["Control", "Shift", "Alt", "Meta"]);

	// Browser keydown handler — active for both formats while capturing.
	// For evdev: runs in parallel with engine capture (fallback if engine
	// has no listener, e.g. macOS daemon mode). Captures any key including
	// pure modifiers (Right ⌘, Left Shift, etc.).
	// For shortcut: captures key combos (skips pure modifier presses).
	function handleKeyDown(e: KeyboardEvent) {
		if (!capturing) return;
		e.preventDefault();
		e.stopPropagation();
		if (e.key === "Escape") { stopCapture(); return; }

		if (format === "evdev") {
			const evdev = codeToEvdev(e.code);
			onchange(evdev);
			stopCapture();
		} else {
			const shortcut = eventToShortcut(e);
			if (!shortcut) return; // pure modifier press, keep waiting
			onchange(shortcut);
			stopCapture();
		}
	}

	function stopCapture() {
		abortController?.abort();
		abortController = null;
		capturing = false;
	}

	async function startCapture() {
		if (capturing) { stopCapture(); return; }
		capturing = true;

		if (format === "evdev") {
			// Try engine-side capture (works on Linux, macOS with bindings).
			// Browser keydown is armed simultaneously as fallback — if the
			// engine has no listener (macOS daemon mode), browser captures.
			// Whichever fires first wins; stopCapture() aborts the other.
			abortController = new AbortController();
			try {
				const key = await captureHotkey(abortController.signal);
				if (key && key !== "KEY_ESC" && capturing) onchange(key);
			} catch {
				// Aborted (browser keydown fired first) or fetch failed
			} finally {
				capturing = false;
				abortController = null;
			}
		}
		// shortcut mode: capturing=true arms the keydown handler above
	}
</script>

<svelte:window onkeydown={handleKeyDown} />

<div class="flex items-center gap-2">
	<!-- Current value display -->
	<div class="min-w-[6rem] flex items-center">
		{#if capturing}
			<span class="text-xs text-muted-foreground italic animate-pulse">
				{format === "evdev" ? "Press a key…" : "Press combination…"}
			</span>
		{:else if display}
			<kbd class="inline-flex items-center rounded border border-border bg-muted px-2 py-0.5
				text-sm font-mono font-medium text-foreground shadow-sm">
				{display}
			</kbd>
		{:else}
			<span class="text-sm text-muted-foreground">—</span>
		{/if}
	</div>

	<Button
		size="sm"
		variant={capturing ? "destructive" : "outline"}
		onclick={startCapture}
	>
		{capturing ? "Cancel" : "Capture"}
	</Button>
</div>
