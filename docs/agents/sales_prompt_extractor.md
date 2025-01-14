# Sales Prompt Extractor Agent

## Overview
The Sales Prompt Extractor agent analyzes video/audio content to extract sales techniques, concepts, and generate AI voice agent prompts.

## Data Structure

### Analysis Results
```json
{
    "analysis_id": "unique_id",
    "source": {
        "video_id": "video_reference",
        "timestamp": "ISO-8601-timestamp",
        "duration": "duration_in_seconds"
    },
    "structured_analysis": {
        "sales_techniques": [
            {
                "name": "technique_name",
                "description": "detailed_description",
                "examples": ["example1", "example2"],
                "context": "usage_context"
            }
        ],
        "communication_strategies": [
            {
                "type": "strategy_type",
                "description": "strategy_description",
                "application": "how_to_apply"
            }
        ],
        "objection_handling": [
            {
                "objection_type": "type",
                "recommended_response": "response",
                "examples": ["example1", "example2"]
            }
        ]
    },
    "text_summary": "comprehensive_text_analysis",
    "metadata": {
        "domain": "sales_domain",
        "industry": "specific_industry",
        "target_audience": "audience_type"
    }
}
```

### Prompt Versions
```json
{
    "prompt_id": "unique_id",
    "version": "version_number",
    "created_at": "ISO-8601-timestamp",
    "analysis_ref": "analysis_id_reference",
    "prompt_content": {
        "system_prompt": "main_prompt_text",
        "first_message": "initial_greeting",
        "example_conversations": ["example1", "example2"]
    },
    "tags": ["domain_tag", "context_tag"],
    "metadata": {
        "author": "generator_info",
        "source_video": "video_reference",
        "performance_metrics": {
            "engagement_rate": "metric",
            "conversion_rate": "metric"
        }
    }
}
```

## Implementation Phases

### Phase 1: Core Analysis (Current)
- [ ] Basic concept extraction from transcripts
- [ ] Initial prompt generation
- [ ] Session data storage
- [ ] Integration with existing transcription agent

### Phase 2: Advanced Analysis
- [ ] Enhanced sales technique detection
- [ ] Pattern recognition across multiple videos
- [ ] Structured data validation
- [ ] Performance metrics tracking

### Phase 3: Optimization
- [ ] Machine learning model integration
- [ ] Real-time analysis capabilities
- [ ] Batch processing support
- [ ] Analysis quality metrics

## Usage

```python
# Example usage (planned)
extractor = SalesPromptExtractor(session)
analysis = await extractor.analyze_video(video_id)
prompt = await extractor.generate_prompt(analysis_id)
```

## Integration Points
- Transcription Agent
- Video Upload Agent
- Web Search Agent
- ElevenLabs Conversation Agent 