<template>
  <div class="yaml-display">
    <pre v-if="yamlContent" class="yaml-content">{{ yamlContent }}</pre>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  content: {
    type: Object,
    required: true
  }
});

const yamlContent = computed(() => {
  if (props.content && props.content.yaml_data) {
    return JSON.stringify(props.content.yaml_data, null, 2);
  }
  return null;
});
</script>

<style scoped>
.yaml-display {
  background: #1e1e1e;
  border-radius: 8px;
  padding: 16px;
  margin: 8px 0;
  overflow-x: auto;
}

.yaml-content {
  font-family: 'Courier New', Courier, monospace;
  color: #d4d4d4;
  white-space: pre-wrap;
  margin: 0;
}
</style> 