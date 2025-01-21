<template>
  <div class="analysis-display">
    <!-- Analysis Section -->
    <div v-if="parsedContent.analysis" class="analysis-section">
      <h3>Analysis</h3>
      <div class="content-text markdown-content" v-html="parsedContent.analysis"></div>
    </div>
    
    <!-- Structured Data Section -->
    <div v-if="hasStructuredData" class="structured-data-section">
      <h3>Structured Data</h3>
      <div v-for="(value, key) in parsedContent.structured_data" :key="key" class="structured-data-item">
        <h4>{{ key }}</h4>
        <pre class="code-block">{{ JSON.stringify(value, null, 2) }}</pre>
      </div>
    </div>
    
    <!-- Voice Prompt Section -->
    <div v-if="parsedContent.voice_prompt && parsedContent.voice_prompt.length > 0" class="voice-prompt-section">
      <h3>Voice Prompt</h3>
      <div class="content-text voice-prompt">{{ parsedContent.voice_prompt }}</div>
    </div>

    <!-- Debug Info (only in development) -->
    <div v-if="import.meta.env.DEV" class="debug-info">
      <h4>Debug Info:</h4>
      <pre>{{ JSON.stringify({
        rawContentType: typeof props.content,
        messageType: props.content?.type,
        isSocketMessage: props.content?.msg_type === 'output',
        isAnalysisResults: props.content?.type === 'analysis_results',
        hasContent: !!props.content?.content,
        contentLength: props.content?.content?.length,
        hasAnalysis: !!parsedContent.analysis,
        analysisLength: parsedContent.analysis?.length || 0,
        hasStructuredData,
        structuredDataKeys: hasStructuredData ? Object.keys(parsedContent.structured_data) : [],
        hasVoicePrompt: !!parsedContent.voice_prompt,
        voicePromptLength: parsedContent.voice_prompt?.length || 0,
        rawContent: props.content,
        normalizedContent: parsedContent
      }, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  content: {
    type: [Object, Array, String],
    required: true
  }
});

// Helper function to normalize content structure
const normalizeContent = (content) => {
  console.log('Normalizing content:', content);
  
  let processedContent = content;
  
  // If content is a string, try to parse it as JSON
  if (typeof content === 'string') {
    try {
      processedContent = JSON.parse(content);
      console.log('Parsed string content:', processedContent);
    } catch (e) {
      console.error('Error parsing content string:', e);
      return {
        analysis: content,
        structured_data: null,
        voice_prompt: ''
      };
    }
  }

  // If we have a Socket.IO message
  if (processedContent?.msg_type === 'output' && Array.isArray(processedContent?.content)) {
    const textContent = processedContent.content.find(item => 
      item.type === 'text' && 
      item.agent_name === 'sales_prompt_extractor'
    );
    
    if (textContent) {
      console.log('Found sales_prompt_extractor content:', {
        hasText: !!textContent.text,
        hasStructuredData: !!textContent.structured_data,
        hasVoicePrompt: !!textContent.voice_prompt
      });
      
      // Extract all components directly from the textContent
      const normalized = {
        analysis: textContent.text || '',
        structured_data: textContent.structured_data || null,
        voice_prompt: textContent.voice_prompt || ''
      };
      
      console.log('Normalized content components:', normalized);
      return normalized;
    }
  }

  // For direct message content
  const normalized = {
    analysis: processedContent.text || '',
    structured_data: processedContent.structured_data || null,
    voice_prompt: processedContent.voice_prompt || ''
  };
  
  console.log('Direct content components:', normalized);
  return normalized;
};

const parsedContent = computed(() => {
  const content = normalizeContent(props.content);
  console.log('Parsed content:', {
    hasVoicePrompt: !!content.voice_prompt,
    voicePromptLength: content.voice_prompt?.length || 0,
    voicePromptContent: content.voice_prompt
  });
  return content;
});

const hasStructuredData = computed(() => {
  return parsedContent.value.structured_data !== null && 
         Object.keys(parsedContent.value.structured_data || {}).length > 0;
});

const formattedStructuredData = computed(() => {
  try {
    if (!hasStructuredData.value) return '';
    return JSON.stringify(parsedContent.value.structured_data, null, 2);
  } catch (e) {
    console.error('Error formatting structured data:', e);
    return '';
  }
});
</script>

<style scoped>
.analysis-display {
  padding: 1rem;
}

.analysis-section,
.structured-data-section,
.voice-prompt-section {
  margin-bottom: 2rem;
}

h3 {
  color: #2c3e50;
  margin-bottom: 1rem;
  font-size: 1.5rem;
}

h4 {
  color: #34495e;
  margin: 1rem 0;
  font-size: 1.2rem;
  text-transform: capitalize;
}

.content-text {
  line-height: 1.6;
  white-space: pre-wrap;
}

.structured-data-item {
  background: #f8f9fa;
  padding: 1rem;
  border-radius: 4px;
  margin-bottom: 1rem;
}

.code-block {
  background: #f1f1f1;
  padding: 1rem;
  border-radius: 4px;
  overflow-x: auto;
  font-family: monospace;
}

.debug-info {
  margin-top: 2rem;
  padding: 1rem;
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 4px;
}

.debug-info pre {
  white-space: pre-wrap;
  word-break: break-word;
}

.markdown-content :deep(p) {
  margin-bottom: 1rem;
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  margin-left: 1.5rem;
  margin-bottom: 1rem;
}

.voice-prompt-section {
  margin-bottom: 2rem;
  background: #e3f2fd;
  padding: 1.5rem;
  border-radius: 8px;
  border-left: 4px solid #2196f3;
}

.voice-prompt {
  font-style: italic;
  color: #1565c0;
  line-height: 1.8;
}
</style> 