# Sales Analysis

## Overview
The sales analysis functionality in Director provides comprehensive analysis of sales conversations, generating structured insights and voice agent prompts. The system has been consolidated to improve efficiency and reduce redundancy.

## Components

### SalesAnalysisTool
Located in `backend/director/tools/sales_analysis_tool.py`, this is the core component that handles:
- Raw conversation analysis
- Structured data extraction
- Voice prompt generation

### SalesPromptExtractorAgent
Located in `backend/director/agents/sales_prompt_extractor.py`, this agent:
- Coordinates the analysis process
- Handles video transcription
- Manages data storage in Supabase
- Formats output for display

## Output Format
The analysis results are returned in three sections, all formatted in code blocks for clarity:

1. Analysis Section:
```markdown
[Detailed analysis of sales techniques, communication strategies, etc.]
```

2. Structured Data Section:
```json
{
  "sales_techniques": [...],
  "communication_strategies": [...],
  "objection_handling": [...],
  "voice_agent_guidelines": [...]
}
```

3. Voice Prompt Section:
```
[Concise, actionable prompt for AI voice agents]
```

## Storage
Analysis results are stored in multiple locations:
- Supabase vector store for searchable access
- Local SQLite database for quick retrieval
- Generated outputs table for structured data and voice prompts

## Usage
To analyze a sales conversation:
1. Upload a video file
2. Use the command: `@sales_prompt_extractor video_id=<ID> collection_id=<ID>`
3. The system will:
   - Transcribe the video
   - Analyze the conversation
   - Generate structured insights
   - Create a voice agent prompt
   - Store all outputs
   - Return formatted results

## Recent Improvements
- Consolidated analysis logic into `SalesAnalysisTool`
- Improved output formatting with code blocks
- Enhanced socket.io message handling
- Fixed session handling for video_id and collection_id
- Streamlined storage process in Supabase 