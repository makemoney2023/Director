# Sales Prompt Extractor Agent

## Overview
The Sales Prompt Extractor Agent serves as an orchestrator for a suite of specialized agents that analyze sales conversations and generate sophisticated AI voice agent implementations. It coordinates multiple agents to produce structured data, voice prompts, and training data in various formats optimized for LLM consumption.

## Agent Architecture

### Core Agents

#### SalesAnalysisAgent
- Performs detailed analysis of sales conversations
- Generates markdown-formatted analysis
- Uses Anthropic API for deep understanding
- Focuses on sales techniques, communication patterns, and effectiveness

#### VoicePromptGenerationAgent
- Generates natural, contextual voice prompts
- Uses Anthropic API for creative generation
- Adapts to conversation context and style
- Produces markdown with frontmatter format

#### StructuredDataAgent
- Creates JSON-formatted structured data
- Incorporates analysis and voice prompt insights
- Includes metadata for LLM consumption
- Optimized for model training and evaluation

#### YAMLConfigurationAgent
- Generates hierarchical configuration
- Manages system-wide parameters
- Provides clear, readable format
- Supports complex nested structures

#### TrainingPairExtractionAgent
- Extracts input-output training pairs
- Includes context and metadata
- Supports model fine-tuning
- Provides quality metrics

## Data Formats

### Voice Prompt Format
```yaml
metadata:
  version: "1.0"
  type: "voice_generation"
  context: "sales_conversation"

voice_characteristics:
  tone: "professional_warm"
  pace: "natural_adaptive"
  style: "consultative"

conversation_framework:
  opening:
    approach: "..."
    key_elements: [...]
  discovery:
    techniques: [...]
    adaptations: {...}
  closing:
    strategies: [...]
    transitions: {...}

implementation_guidelines:
  core_principles: [...]
  adaptation_rules: {...}
  context_handling: [...]
```

### Structured Analysis Format
```json
{
  "analysis": {
    "techniques": [...],
    "patterns": [...],
    "effectiveness": {...}
  },
  "metadata": {
    "model_instructions": "...",
    "usage_guidelines": "...",
    "version": "..."
  }
}
```

### Training Pairs Format
```json
{
  "training_pairs": [
    {
      "input": "...",
      "output": "...",
      "context": "...",
      "metadata": {...}
    }
  ],
  "quality_metrics": {...}
}
```

## Integration Points

### Current Integrations
- Anthropic API for analysis and generation
- Database for persistent storage
- Event system for agent communication

### Future Integrations
- ElevenLabs for voice synthesis
- Real-time voice agent interaction
- Advanced pathway management
- Cross-agent communication framework

## Error Handling
- Comprehensive error capture
- Cross-agent error propagation
- Fallback mechanisms
- Detailed logging

## Configuration
```python
AGENT_PARAMETERS = {
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
    "required": ["video_id", "collection_id"]
}
```

## Usage Examples

### Basic Usage
```python
extractor = SalesPromptExtractorAgent(session)
response = extractor.run(
    video_id="video_id",
    collection_id="collection_id",
    analysis_type="full"
)
```

### Advanced Usage
```python
# Access individual agents
analysis = extractor.analysis_agent.analyze(video_id)
voice_prompt = extractor.voice_agent.generate(analysis)
structured_data = extractor.structured_agent.process(analysis, voice_prompt)
```