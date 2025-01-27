<template>
  <div class="analysis-display bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
    <!-- Analysis Section -->
    <div v-if="parsedContent.analysis" class="analysis-section">
      <h3 class="text-xl font-bold dark:text-white">Analysis</h3>
      <div class="content-text markdown-content dark:text-gray-100" v-html="parsedContent.analysis"></div>
    </div>
    
    <!-- Structured Data Section -->
    <div v-if="hasStructuredData" class="structured-data-section">
      <h3 class="text-xl font-bold dark:text-white">Available Pathways</h3>
      <div v-if="parsedContent.structured_data.pathways" class="pathway-list">
        <div v-for="pathway in parsedContent.structured_data.pathways" :key="pathway.id" 
             class="pathway-item dark:bg-gray-800 dark:border-gray-700 p-4 mb-4 rounded-lg border">
          <h4 class="text-lg font-semibold dark:text-white">{{ pathway.name }}</h4>
          <div class="text-sm text-gray-600 dark:text-gray-300">
            <p><strong>ID:</strong> {{ pathway.id }}</p>
            <p v-if="pathway.description"><strong>Description:</strong> {{ pathway.description }}</p>
          </div>
        </div>
      </div>
      <div v-else class="structured-data-item dark:bg-gray-800 dark:border-gray-700">
        <h4 class="text-lg font-semibold dark:text-white">{{ key }}</h4>
        <pre class="code-block dark:bg-gray-800 dark:text-gray-100">{{ JSON.stringify(value, null, 2) }}</pre>
      </div>
    </div>
    
    <!-- Voice Prompt Section -->
    <div v-if="parsedContent.voice_prompt && parsedContent.voice_prompt.length > 0" class="voice-prompt-section dark:bg-gray-800 dark:border-blue-500">
      <h3 class="text-xl font-bold dark:text-white">Voice Prompt</h3>
      <div class="content-text voice-prompt dark:text-blue-300">{{ parsedContent.voice_prompt }}</div>
    </div>

    <!-- Debug Info (only in development) -->
    <div v-if="import.meta.env.DEV" class="debug-info dark:bg-gray-800 dark:border-gray-700">
      <h4 class="text-lg font-semibold dark:text-white">Debug Info:</h4>
      <pre class="dark:bg-gray-800 dark:text-gray-100">{{ JSON.stringify({
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
      (item.agent_name === 'sales_prompt_extractor' || item.agent_name === 'bland_ai')
    );
    
    if (textContent) {
      console.log(`Found ${textContent.agent_name} content:`, {
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

.content-text {
  line-height: 1.6;
  white-space: pre-wrap;
}

.structured-data-item {
  padding: 1rem;
  border-radius: 0.5rem;
  margin-bottom: 1rem;
  border-width: 1px;
}

.code-block {
  padding: 1rem;
  border-radius: 0.5rem;
  overflow-x: auto;
  font-family: monospace;
  white-space: pre-wrap;
}

.debug-info {
  margin-top: 2rem;
  padding: 1rem;
  border-radius: 0.5rem;
  border-width: 1px;
}

.voice-prompt-section {
  margin-bottom: 2rem;
  padding: 1.5rem;
  border-radius: 0.5rem;
  border-left-width: 4px;
}

.voice-prompt {
  font-style: italic;
  line-height: 1.8;
}

:deep(.markdown-content p) {
  margin-bottom: 1rem;
}

:deep(.markdown-content ul),
:deep(.markdown-content ol) {
  margin-left: 1.5rem;
  margin-bottom: 1rem;
}
</style> 