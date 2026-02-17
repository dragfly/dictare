<script lang="ts">
	import { Input } from "$lib/components/ui/input";

	interface Props {
		value: string;
		onchange: (value: string) => void;
	}

	let { value, onchange }: Props = $props();
</script>

<Input
	type="text"
	class="max-w-sm"
	{value}
	onchange={(e) => onchange(e.currentTarget.value)}
/>
