import axios from 'axios';

const BACKEND_URL = import.meta.env.VITE_APP_BACKEND_URL;

const api = axios.create({
    baseURL: BACKEND_URL,
    headers: {
        'Content-Type': 'application/json'
    }
});

export const videoService = {
    async uploadVideo(file, collectionId) {
        const formData = new FormData();
        formData.append('video', file);
        formData.append('collection_id', collectionId);
        
        const response = await api.post('/videos/upload', formData, {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
        return response.data;
    },

    async getAnalysis(videoId) {
        const response = await api.get(`/videos/${videoId}/analysis`);
        return response.data;
    },

    async getStructuredData(videoId) {
        const response = await api.get(`/videos/${videoId}/structured-data`);
        return response.data;
    },

    async getVoicePrompt(videoId) {
        const response = await api.get(`/videos/${videoId}/voice-prompt`);
        return response.data;
    }
};

export const analysisService = {
    async startAnalysis(videoId) {
        const response = await api.post('/analysis/start', { video_id: videoId });
        return response.data;
    },

    async getStatus(analysisId) {
        const response = await api.get(`/analysis/${analysisId}/status`);
        return response.data;
    },

    async getResults(analysisId) {
        const response = await api.get(`/analysis/${analysisId}/results`);
        return response.data;
    }
}; 