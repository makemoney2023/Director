<script setup>
import "./style.css";
import { onMounted } from 'vue';

onMounted(() => {
  // Enable dark mode by default
  document.documentElement.classList.add('dark');
});
</script>

<template>
  <div class="w-full h-full template dark:bg-gray-900">
    <router-view />
  </div>
</template>

<style>
:root {
  --popper-theme-background-color: #333333;
  --popper-theme-background-color-hover: #333333;
  --popper-theme-text-color: #ffffff;
  --popper-theme-border-width: 0px;
  --popper-theme-border-style: solid;
  --popper-theme-border-radius: 8px;
  --popper-theme-padding: 4px 8px;
  --popper-theme-box-shadow: 0px 6px 6px rgba(0, 0, 0, 0.08);
}

html {
  overflow: hidden;
  @apply bg-white dark:bg-gray-900;
}

body {
  @apply text-gray-900 dark:text-gray-100;
}
</style>
