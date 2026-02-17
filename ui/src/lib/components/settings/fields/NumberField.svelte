<script lang="ts">
	import { Input } from "$lib/components/ui/input";

	interface Props {
		value: number | null;
		step: number;
		onchange: (value: number) => void;
	}

	let { value, step = 1, onchange }: Props = $props();
</script>

<Input
	type="number"
	class="max-w-[200px]"
	{step}
	value={value ?? ""}
	onchange={(e) => {
		const v = step === 1 ? parseInt(e.currentTarget.value, 10) : parseFloat(e.currentTarget.value);
		if (!isNaN(v)) onchange(v);
	}}
/>
