<script lang="ts">
	import SettingsLayout from "$lib/components/settings/SettingsLayout.svelte";
	import { tabs } from "$lib/registry/tabs";
</script>

<svelte:head>
	<title>Dictare Settings</title>
</svelte:head>

<SettingsLayout {tabs} />
