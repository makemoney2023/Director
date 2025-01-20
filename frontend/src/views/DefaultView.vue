<script setup>
import { ref, onMounted, onUnmounted } from "vue";
import { ChatInterface } from "@videodb/chat-vue";
import "@videodb/chat-vue/dist/style.css";
import { videoService, analysisService } from "../services/api";

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
    />
  </main>
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

.template {
  height: 100vh;
  width: 100vw;
}

main {
  overflow: scroll;
  height: 100%;
}
html {
  overflow: hidden;
}

/* For WebKit-based browsers (Chrome, Safari) */
::-webkit-scrollbar {
  width: 12px; /* Width of the scrollbar */
}

::-webkit-scrollbar-track {
  background: #f1f1f1; /* Background of the scrollbar track */
}

::-webkit-scrollbar-thumb {
  background-color: #888; /* Scrollbar thumb color */
  border-radius: 6px; /* Rounded corners */
  border: 3px solid #f1f1f1; /* Space around the thumb */
}

::-webkit-scrollbar-thumb:hover {
  background-color: #555; /* Thumb color on hover */
}

/* For Mozilla Firefox */
* {
  scrollbar-width: thin; /* Makes the scrollbar narrower */
  scrollbar-color: #888 #f1f1f1; /* Thumb and track colors */
}
</style>
