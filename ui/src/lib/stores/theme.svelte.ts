const STORAGE_KEY = "dictare-theme";

export type Theme = "light" | "dark" | "system";

let theme = $state<Theme>((localStorage.getItem(STORAGE_KEY) as Theme) || "system");

export function getTheme(): Theme {
	return theme;
}

export function setTheme(t: Theme): void {
	theme = t;
	localStorage.setItem(STORAGE_KEY, t);
	applyTheme(t);
}

export function applyTheme(t: Theme): void {
	const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
	const dark = t === "dark" || (t === "system" && prefersDark);
	document.documentElement.classList.toggle("dark", dark);
}
