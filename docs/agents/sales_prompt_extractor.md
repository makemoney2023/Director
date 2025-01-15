# Sales Prompt Extractor Agent

## Overview
The Sales Prompt Extractor Agent analyzes sales conversations and generates structured data and voice agent prompts. It uses a combination of Anthropic AI for detailed analysis and OpenAI for structured data extraction.

## Key Features
- Sales conversation analysis
- Structured data extraction
- Voice agent prompt generation
- Persistent storage of all components
- Future integration with voice synthesis

## Components

### SalesAnalysisContent
Content type for storing sales analysis results:
```python
class SalesAnalysisContent(TextContent):
    analysis_data: Dict = {}  # Structured analysis data
    anthropic_response: Optional[AnthropicResponse] = None  # Raw Anthropic response
    voice_prompt: Optional[str] = None  # Generated voice agent prompt
```

### AnthropicResponse
Model for storing Anthropic API responses:
```python
class AnthropicResponse(BaseModel):
    content: str  # Response content
    timestamp: datetime  # Response timestamp
    status: str  # Response status
    metadata: Dict = {}  # Additional metadata
```

## Data Structures

### Structured Analysis Data
```json
{
    "sales_techniques": [
        {
            "name": "technique name",
            "description": "detailed description with examples"
        }
    ],
    "communication_strategies": [
        {
            "type": "strategy type",
            "description": "detailed description with examples"
        }
    ],
    "objection_handling": [
        {
            "name": "approach name",
            "description": "detailed description with examples"
        }
    ],
    "voice_agent_guidelines": [
        {
            "name": "guideline name",
            "description": "detailed description with examples"
        }
    ]
}
```

### Voice Agent Prompt
The voice agent prompt follows a structured format:
```
SALES CONVERSATION GUIDELINES

CORE OBJECTIVES:
[List of core objectives]

ETHICAL GUIDELINES:
[List of ethical guidelines]

AVAILABLE TECHNIQUES AND STRATEGIES:
[Techniques from analysis]
[Strategies from analysis]
[Objection handling from analysis]
[Voice agent guidelines from analysis]

IMPLEMENTATION GUIDELINES:
[List of implementation guidelines]
```

## Usage

### Basic Usage
```python
agent = SalesPromptExtractorAgent(session)
response = agent.run(
    video_id="video_id",
    collection_id="collection_id",
    analysis_type="full",
    bypass_reasoning=True
)
```

### Response Format
```python
AgentResponse(
    status=AgentStatus.SUCCESS,
    message="Analysis completed successfully",
    data={
        "analysis": "Raw analysis text",
        "voice_prompt": "Formatted voice prompt",
        "structured_data": {
            # Structured analysis data
        }
    }
)
```

## Integration Points

### Current Integrations
- Anthropic AI for conversation analysis
- OpenAI for structured data extraction
- Database for persistent storage

### Future Integrations
- ElevenLabs for voice synthesis
- Real-time voice agent interaction
- Analytics and performance tracking

## Error Handling
- Retry mechanism for API calls
- Error storage in database
- Detailed error logging
- Fallback responses

## Configuration
```python
SALES_PROMPT_PARAMETERS = {
    "type": "object",
    "properties": {
        "video_id": {"type": "string"},
        "collection_id": {"type": "string"},
        "analysis_type": {
            "type": "string",
            "enum": ["sales_techniques", "communication", "full"]
        },
        "output_format": {
            "type": "string",
            "enum": ["structured", "text", "both"]
        }
    },
    "required": ["video_id", "collection_id"],
    "bypass_reasoning": True
} 