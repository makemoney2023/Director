<template>
  <div class="analysis-display">
    <div v-if="content.analysis" class="analysis-section">
      <h3>Analysis</h3>
      <div class="content-text">{{ content.analysis }}</div>
    </div>
    
    <div v-if="content.yaml_config" class="yaml-section">
      <h3>YAML Configuration</h3>
      <pre class="code-block">{{ content.yaml_config }}</pre>
    </div>
    
    <div v-if="content.structured_data" class="structured-data-section">
      <h3>Structured Data</h3>
      <pre class="code-block">{{ formattedStructuredData }}</pre>
    </div>
    
    <div v-if="content.voice_prompt" class="voice-prompt-section">
      <h3>Voice Prompt</h3>
      <div class="content-text">{{ content.voice_prompt }}</div>
    </div>
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

const formattedStructuredData = computed(() => {
  if (props.content.structured_data) {
    return JSON.stringify(props.content.structured_data, null, 2);
  }
  return '';
});
</script>

<style scoped>
.analysis-display {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  width: 100%;
}

.analysis-section,
.yaml-section,
.structured-data-section,
.voice-prompt-section {
  background: #1e1e1e;
  border-radius: 8px;
  padding: 1rem;
}

h3 {
  color: #e0e0e0;
  margin-top: 0;
  margin-bottom: 0.5rem;
  font-size: 1rem;
}

.content-text {
  color: #d4d4d4;
  white-space: pre-wrap;
  font-family: 'Courier New', Courier, monospace;
}

.code-block {
  background: #2d2d2d;
  padding: 1rem;
  border-radius: 4px;
  margin: 0;
  overflow-x: auto;
  color: #d4d4d4;
  font-family: 'Courier New', Courier, monospace;
}
</style> 