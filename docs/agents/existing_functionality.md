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

### Sales Prompt Extractor Agent (`sales_prompt_extractor.py`)
```python
class SalesPromptExtractorAgent(BaseAgent):
    """Sales conversation analysis and prompt generation"""
    capabilities:
    - Analyze sales conversations using Anthropic AI
    - Extract structured data using OpenAI
    - Generate voice agent prompts
    - Store analysis results and prompts
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
- SalesAnalysisContent: Sales analysis and prompt data

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

## Data Structures

### SalesAnalysisContent
```json
{
    "agent_name": "sales_prompt_extractor",
    "status": "success|error|progress",
    "status_message": "Status description",
    "text": "Formatted analysis text",
    "analysis_data": {
        "sales_techniques": [
            {"name": "technique name", "description": "detailed description"}
        ],
        "communication_strategies": [
            {"type": "strategy type", "description": "detailed description"}
        ],
        "objection_handling": [
            {"name": "approach name", "description": "detailed description"}
        ],
        "voice_agent_guidelines": [
            {"name": "guideline name", "description": "detailed description"}
        ]
    },
    "anthropic_response": {
        "content": "Raw analysis text",
        "timestamp": "ISO timestamp",
        "status": "success|error",
        "metadata": {}
    },
    "voice_prompt": "Formatted voice agent prompt"
}
```

### Voice Agent Prompt Structure
```
SALES CONVERSATION GUIDELINES

CORE OBJECTIVES:
1. Build genuine rapport with customers
2. Understand customer needs and pain points
3. Present relevant solutions effectively
4. Address concerns and objections professionally
5. Guide conversations toward positive outcomes

ETHICAL GUIDELINES:
1. Always be truthful and transparent
2. Never pressure customers into decisions
3. Respect customer privacy and confidentiality
4. Only make promises you can keep
5. Prioritize customer needs over immediate sales

AVAILABLE TECHNIQUES AND STRATEGIES:
- Sales Techniques (from analysis)
- Communication Strategies (from analysis)
- Objection Handling (from analysis)
- Voice Agent Guidelines (from analysis)

IMPLEMENTATION GUIDELINES:
1. Start conversations by building rapport and understanding needs
2. Use appropriate sales techniques based on the conversation context
3. Address objections using the provided strategies
4. Apply closing techniques naturally when customer shows interest
5. Maintain a helpful and consultative approach throughout

### Integration Points
- Anthropic AI for conversation analysis
- OpenAI for structured data extraction
- Database storage for analysis results
- Future integration with ElevenLabs for voice synthesis

### Workflow
1. Receive sales conversation transcript
2. Generate analysis using Anthropic AI
3. Extract structured data using OpenAI
4. Generate voice agent prompt
5. Store all data in database
6. Return formatted response with all components 