<script lang="ts">
	import SettingsLayout from "$lib/components/settings/SettingsLayout.svelte";
	import { tabs } from "$lib/generated/tabs";
</script>

<svelte:head>
	<title>VoxType Settings</title>
</svelte:head>

<SettingsLayout {tabs} />
