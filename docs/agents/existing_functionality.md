# Existing Functionality Overview

## Core Agents

### Transcription Agent (`transcription.py`)
```python
class TranscriptionAgent(BaseAgent):
    """Handles video/audio transcription"""
    capabilities:
    - Generate transcripts from video/audio
    - Basic text processing
    - Integration with speech-to-text services
```

### Summarization Agent (`summarize_video.py`)
```python
class SummarizeVideoAgent(BaseAgent):
    """Video content summarization"""
    capabilities:
    - Extract key points from video content
    - Generate concise summaries
    - Process transcripts for main themes
```

### Audio Generation Agent (`audio_generation.py`)
```python
class AudioGenerationAgent(BaseAgent):
    """Audio synthesis and processing"""
    capabilities:
    - Text-to-speech conversion
    - Voice synthesis
    - Audio format handling
```

### Upload Agent (`upload.py`)
```python
class UploadAgent(BaseAgent):
    """File upload handling"""
    capabilities:
    - Video/audio file upload
    - Format validation
    - Storage management
```

### Web Search Agent (`web_search_agent.py`)
```python
class WebSearchAgent(BaseAgent):
    """Web content retrieval"""
    capabilities:
    - YouTube video fetching
    - URL content processing
    - Web resource management
```

## Core Infrastructure

### Base Agent (`base.py`)
```python
class BaseAgent:
    """Foundation for all agents"""
    features:
    - Session management
    - State handling
    - Error management
    - Event processing
```

### Session Management
```python
class Session:
    """Manages agent sessions and state"""
    features:
    - Data persistence
    - State tracking
    - Message handling
    - Content type management
```

## Content Types
- TextContent: Text-based outputs
- VideoContent: Video processing results
- AudioContent: Audio processing outputs
- SearchResultContent: Search operation results

## Integration Points

### Internal Connections
- Agent-to-agent communication
- Shared session state
- Content type conversion
- Event propagation

### External Services
- Video processing APIs
- Speech-to-text services
- Storage systems
- Search services

## Key Workflows

### Video Processing
1. Upload/URL input
2. Transcription
3. Analysis/Summarization
4. Result generation

### Content Analysis
1. Content ingestion
2. Text extraction
3. Analysis processing
4. Output formatting

### Audio Processing
1. Text input
2. Voice synthesis
3. Audio generation
4. Format conversion

## Existing Data Structures

### Session Data
```json
{
    "session_id": "unique_id",
    "created_at": "timestamp",
    "state": "status",
    "content": {
        "type": "content_type",
        "data": {}
    },
    "metadata": {}
}
```

### Message Format
```json
{
    "message_id": "unique_id",
    "type": "message_type",
    "content": {},
    "status": "status_code",
    "timestamp": "iso_timestamp"
}
```

## Common Utilities
- Error handling
- Logging
- State management
- Format conversion
- API integration helpers

## Extension Points
- Agent inheritance
- Message handlers
- Content type expansion
- Service integration
- State management hooks 