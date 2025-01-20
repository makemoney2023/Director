# Edge Functions Architecture for Sales Prompt Generation

## Overview
This document outlines the architecture and data flow for the sales prompt generation system using Supabase Edge Functions. The system processes sales conversations synchronously, utilizing Edge Functions for computationally intensive tasks while maintaining a synchronous request-response cycle.

## System Architecture

```mermaid
graph TD
    A[Frontend] -->|1. Select Video| B[Sales Prompt Extractor]
    B -->|2. Get Transcript| C[Transcription Service]
    B -->|3. Chunk & Embed| D[(Supabase pgvector)]
    B -->|4. Call| E[Edge Function 1: Structured Data]
    E -->|5. OpenAI Analysis| F[(generated_outputs)]
    B -->|6. Call| G[Edge Function 2: Voice Prompt]
    G -->|7. Claude Generation| H[(generated_outputs)]
    B -->|8. Complete Response| A
```

## Data Flow Stages

### 1. Initial Processing (Synchronous)
- Frontend selects video from collection
- `@sales_prompt_extractor` agent:
  - Retrieves video transcript
  - Chunks transcript into segments
  - Generates embeddings using OpenAI
  - Stores in Supabase pgvector
  - Waits for completion

### 2. Structured Data Generation (Synchronous)
```mermaid
sequenceDiagram
    participant BE as Backend
    participant EF1 as Edge Function 1
    participant OpenAI as OpenAI API
    participant DB as Supabase DB
    
    BE->>EF1: Direct call
    EF1->>OpenAI: Send for analysis
    OpenAI->>EF1: Return structured data
    EF1->>DB: Store in generated_outputs
    EF1->>BE: Return result
```

- Direct call from backend
- Process:
  - Retrieves relevant transcript chunks
  - Sends to OpenAI for structured analysis
  - Stores result in `generated_outputs` table
  - Returns result to backend
  - Type: `structured_data`

### 3. Voice Prompt Generation (Synchronous)
```mermaid
sequenceDiagram
    participant BE as Backend
    participant EF2 as Edge Function 2
    participant Claude as Claude API
    participant DB as Supabase DB
    
    BE->>EF2: Direct call
    EF2->>Claude: Generate voice prompt
    Claude->>EF2: Return voice prompt
    EF2->>DB: Store in generated_outputs
    EF2->>BE: Return result
```

- Direct call from backend
- Process:
  - Uses structured data from previous step
  - Sends to Claude for voice prompt generation
  - Stores result in `generated_outputs` table
  - Returns result to backend
  - Type: `voice_prompt`

## Database Schema

### videos
```sql
CREATE TABLE videos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id TEXT NOT NULL,
    collection_id TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(video_id, collection_id)
);
```

### transcripts
```sql
CREATE TABLE transcripts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id UUID REFERENCES videos(id),
    full_text TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### transcript_chunks
```sql
CREATE TABLE transcript_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transcript_id UUID REFERENCES transcripts(id),
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    embedding vector(1536),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### generated_outputs
```sql
CREATE TABLE generated_outputs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id UUID REFERENCES videos(id),
    output_type TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

## Frontend Integration

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant BE as Backend
    participant SB as Supabase
    
    FE->>BE: Select video
    BE->>SB: Process transcript
    BE->>SB: Call Edge Function 1
    BE->>SB: Call Edge Function 2
    BE->>FE: Return complete response
```

### Response Structure
```typescript
interface AnalysisResponse {
  status: 'success' | 'error';
  data: {
    analysis: string;
    structured_data: Record<string, any>;
    voice_prompt: string;
  };
  metadata: {
    processing_time: number;
    stages_completed: string[];
  };
}
```

## Error Handling

### Edge Function Error Handling
```mermaid
graph TD
    A[Edge Function] -->|Try| B{Success?}
    B -->|No| C[Return Error]
    C --> D[Backend Handles Error]
    B -->|Yes| E[Return Result]
    E --> F[Continue Processing]
```

- Immediate error reporting
- No retry mechanism (handled by backend if needed)
- Detailed error information
- Transaction rollback if needed

## Monitoring and Logging

### Key Metrics
- Total processing time
- Time per processing stage
- API call success rates
- Error frequency by type

### Log Structure
```json
{
  "request_id": "uuid",
  "video_id": "uuid",
  "timestamp": "ISO-8601",
  "duration_ms": 1234,
  "stages": {
    "transcript_processing": {
      "status": "success",
      "duration_ms": 500
    },
    "structured_data": {
      "status": "success",
      "duration_ms": 400
    },
    "voice_prompt": {
      "status": "success",
      "duration_ms": 300
    }
  }
}
```

## Implementation Phases

### Phase 1: Edge Function Development
- Develop Edge Functions for structured data and voice prompt generation
- Implement proper error handling
- Add comprehensive logging

### Phase 2: Integration
- Integrate Edge Functions with existing synchronous flow
- Ensure proper error propagation
- Validate response times

### Phase 3: Testing
- Load testing
- Error scenario testing
- End-to-end flow validation

### Phase 4: Optimization
- Optimize Edge Function performance
- Fine-tune error handling
- Enhance monitoring 