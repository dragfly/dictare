<script lang="ts">
	import "../app.css";
	import * as Tooltip from "$lib/components/ui/tooltip";

	let { children } = $props();
</script>

<Tooltip.Provider>
	{@render children()}
</Tooltip.Provider>
