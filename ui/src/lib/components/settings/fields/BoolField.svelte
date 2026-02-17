<script lang="ts">
	import { Switch } from "$lib/components/ui/switch";

	interface Props {
		checked: boolean;
		onchange: (value: boolean) => void;
	}

	let { checked, onchange }: Props = $props();
</script>

<Switch
	{checked}
	onCheckedChange={(v) => onchange(v)}
/>
