<script setup>
import { ref, onMounted, onUnmounted } from "vue";
import { ChatInterface } from "@videodb/chat-vue";
import "@videodb/chat-vue/dist/style.css";
import { videoService, analysisService } from "../services/api";
import Logo from "../components/Logo.vue";
import SidebarIcon from "../components/SidebarIcon.vue";

const BACKEND_URL = import.meta.env.VITE_APP_BACKEND_URL;
const chatInterfaceRef = ref(null);

// Handle Edge Function responses
const handleAnalysisResponse = async (response) => {
  if (response.type === 'analysis_complete') {
    const results = await analysisService.getResults(response.analysis_id);
    chatInterfaceRef.value.appendSystemMessage({
      type: 'analysis_results',
      content: results
    });
  }
};

// Handle video upload and analysis
const handleVideoUpload = async (file, collectionId) => {
  try {
    // Upload video
    const uploadResponse = await videoService.uploadVideo(file, collectionId);
    
    // Start analysis
    const analysisResponse = await analysisService.startAnalysis(uploadResponse.video_id);
    
    // Show progress message
    chatInterfaceRef.value.appendSystemMessage({
      type: 'progress',
      content: 'Analysis started...'
    });

    // Poll for status
    const pollStatus = async () => {
      const status = await analysisService.getStatus(analysisResponse.analysis_id);
      if (status.status === 'completed') {
        handleAnalysisResponse({
          type: 'analysis_complete',
          analysis_id: analysisResponse.analysis_id
        });
      } else if (status.status === 'failed') {
        chatInterfaceRef.value.appendSystemMessage({
          type: 'error',
          content: 'Analysis failed: ' + status.error
        });
      } else {
        setTimeout(pollStatus, 2000); // Poll every 2 seconds
      }
    };
    pollStatus();
  } catch (error) {
    chatInterfaceRef.value.appendSystemMessage({
      type: 'error',
      content: 'Error processing video: ' + error.message
    });
  }
};

const handleKeyDown = (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "k") {
    event.preventDefault();
    chatInterfaceRef.value.createNewSession();
    chatInterfaceRef.value.chatInputRef.focus();
  }
};

onMounted(() => {
  window.addEventListener("keydown", handleKeyDown);
});

onUnmounted(() => {
  window.removeEventListener("keydown", handleKeyDown);
});
</script>

<template>
  <main>
    <chat-interface
      ref="chatInterfaceRef"
      :chat-hook-config="{
        socketUrl: `${BACKEND_URL}/chat`,
        httpUrl: `${BACKEND_URL}`,
        debug: true,
        handlers: {
          onVideoUpload: handleVideoUpload,
          onAnalysisResponse: handleAnalysisResponse
        }
      }"
      :logo-component="Logo"
      :sidebar-config="{
        icon: SidebarIcon,
        links: [
          {
            href: 'https://docs.director.videodb.io/',
            text: 'Documentation'
          },
          {
            href: 'https://discord.com/invite/py9P639jGz',
            text: 'Support'
          }
        ]
      }"
    />
  </main>
</template>

<style>
/* Base theme variables */
:root {
  --vdb-primary: #9c27b0;
  --vdb-primary-dark: #7b1fa2;
  --vdb-bg-dark: #121212;
  --vdb-card-bg: #1e1e1e;
  --vdb-border: #2d2d2d;
  --vdb-text: #ffffff;
  --vdb-highlight-bg: #2a2a2a;
}

/* Global text color */
*, *::before, *::after {
  color: var(--vdb-text) !important;
}

/* Selection styles */
::selection {
  background-color: var(--vdb-primary) !important;
  color: var(--vdb-text) !important;
}

::-moz-selection {
  background-color: var(--vdb-primary) !important;
  color: var(--vdb-text) !important;
}

/* Title styles - now white instead of gradient */
.collection-title,
div[title="VideoDB Default Collection"],
[class*="vdb-c-line-clamp"] {
  color: var(--vdb-text) !important;
  -webkit-text-fill-color: var(--vdb-text) !important;
  background-image: none !important;
}

/* Global background */
body, html, main, .chat-interface {
  background-color: var(--vdb-bg-dark) !important;
}

/* Primary color overrides with high specificity */
.vdb-c-text-orange,
div.vdb-c-text-orange,
span.vdb-c-text-orange {
  color: var(--vdb-primary) !important;
}

.vdb-c-bg-orange,
div.vdb-c-bg-orange,
button.vdb-c-bg-orange {
  background-color: var(--vdb-primary) !important;
}

.vdb-c-border-orange,
div.vdb-c-border-orange {
  border-color: var(--vdb-primary) !important;
}

/* Hover states */
.vdb-c-hover\:bg-orange:hover,
div.vdb-c-hover\:bg-orange:hover,
button.vdb-c-hover\:bg-orange:hover {
  background-color: var(--vdb-primary-dark) !important;
}

.vdb-c-hover\:text-orange:hover,
div.vdb-c-hover\:text-orange:hover {
  color: var(--vdb-primary) !important;
}

/* Icons */
.query-card-icon path,
svg path.vdb-c-fill-orange {
  fill: var(--vdb-primary) !important;
}

/* Card styles with high specificity */
.chat-card,
.query-card,
div.chat-card,
div.query-card,
:deep(.chat-card),
:deep(.query-card),
.vdb-c-bg-white {
  background-color: var(--vdb-card-bg) !important;
  border: 1px solid var(--vdb-border) !important;
}

/* Card text color override */
.chat-card *,
.query-card *,
div.chat-card *,
div.query-card *,
:deep(.chat-card) *,
:deep(.query-card) *,
.vdb-c-bg-white * {
  color: var(--vdb-text) !important;
}

/* Selected text in cards */
.chat-card ::selection,
.query-card ::selection,
div.chat-card ::selection,
div.query-card ::selection {
  background-color: var(--vdb-primary) !important;
  color: var(--vdb-text) !important;
}

/* Button styles */
.vdb-c-btn,
button.vdb-c-btn,
:deep(.vdb-c-btn) {
  background-color: var(--vdb-primary) !important;
  color: var(--vdb-text) !important;
}

.vdb-c-btn:hover,
button.vdb-c-btn:hover,
:deep(.vdb-c-btn:hover) {
  background-color: var(--vdb-primary-dark) !important;
}

/* Light variants */
.vdb-c-bg-orange-light,
div.vdb-c-bg-orange-light {
  background-color: rgba(156, 39, 176, 0.1) !important;
}

/* Dark variants */
.vdb-c-bg-orange-dark,
div.vdb-c-bg-orange-dark {
  background-color: var(--vdb-primary-dark) !important;
}

/* Interface elements */
:deep(.chat-interface),
:deep(.sidebar),
:deep(.chat-messages),
:deep(.main-content),
.chat-interface,
.sidebar,
.chat-messages,
.main-content {
  background-color: var(--vdb-bg-dark) !important;
}

/* Message styling */
:deep(.message),
.message {
  background-color: var(--vdb-card-bg) !important;
  border-color: var(--vdb-border) !important;
}

/* Input fields */
:deep(input),
:deep(textarea),
input,
textarea,
.vdb-c-bg-gray-50 {
  background-color: var(--vdb-card-bg) !important;
  border-color: var(--vdb-border) !important;
}

/* Collection items */
:deep(.collection-item),
:deep(.chat-item),
.collection-item,
.chat-item {
  background-color: var(--vdb-card-bg) !important;
  border-color: var(--vdb-border) !important;
}

:deep(.collection-item:hover),
:deep(.chat-item:hover),
.collection-item:hover,
.chat-item:hover {
  background-color: var(--vdb-highlight-bg) !important;
}

/* Upload button */
:deep(.upload-btn),
.upload-btn,
button.upload-btn {
  background-color: var(--vdb-primary) !important;
  color: var(--vdb-text) !important;
}

:deep(.upload-btn:hover),
.upload-btn:hover,
button.upload-btn:hover {
  background-color: var(--vdb-primary-dark) !important;
}

/* Scrollbar styling */
::-webkit-scrollbar {
  width: 12px;
}

::-webkit-scrollbar-track {
  background: var(--vdb-card-bg);
}

::-webkit-scrollbar-thumb {
  background-color: #424242;
  border-radius: 6px;
  border: 3px solid var(--vdb-card-bg);
}

::-webkit-scrollbar-thumb:hover {
  background-color: #616161;
}

* {
  scrollbar-width: thin;
  scrollbar-color: #424242 var(--vdb-card-bg);
}

/* Additional overrides for light backgrounds */
.vdb-c-bg-gray-50,
.vdb-c-bg-white,
div.vdb-c-bg-gray-50,
div.vdb-c-bg-white {
  background-color: var(--vdb-card-bg) !important;
}

/* Force white text on all elements */
:deep(*),
* {
  color: var(--vdb-text) !important;
}
</style>
