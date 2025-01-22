# Data Flow Documentation

## Overview
This document describes how data flows between the backend and frontend of the Director application, including both REST API and WebSocket communications.

## Backend to Frontend Communication

### 1. WebSocket Communication (Socket.IO)
The application uses Socket.IO for real-time bidirectional communication.

#### Backend Setup (`backend/director/entrypoint/api/socket_io.py`)
- Socket.IO server implements `ChatNamespace` class
- Key event handlers:
  - `on_connect()` - Handles new client connections
  - `on_disconnect()` - Manages client disconnections
  - `on_reconnect(data)` - Handles reconnection with session recovery
  - `on_chat(message)` - Processes chat messages and returns responses

#### Error Recovery
- Implements retry logic for failed message emissions (3 attempts)
- Stores and recovers last responses for session continuity
- Handles database reconnection automatically

#### Frontend Integration (`frontend/src/views/DefaultView.vue`)
- Uses `@videodb/chat-vue` component library
- Configures Socket.IO client with:
  ```javascript
  chatHookConfig: {
    socketUrl: `${BACKEND_URL}/chat`,
    httpUrl: `${BACKEND_URL}`,
    debug: true
  }
  ```
- Implements keyboard shortcuts (Ctrl/Cmd + K) for new sessions

### 2. Message Flow

#### Chat Message Structure
```typescript
interface ChatMessage {
  session_id: string;      // Unique session identifier
  conv_id: string;         // Conversation ID within session
  msg_type: 'input' | 'output';
  content: MessageContent[];
  actions?: string[];      // Available actions
  agents?: string[];       // Active agents
  metadata?: {
    timestamp: string;
    [key: string]: any;
  }
}
```

#### Response Handling
1. Backend Processing:
   - Validates incoming messages
   - Creates new sessions if needed
   - Processes through chat handler
   - Adds metadata and timestamps
   - Implements retry logic for failed emissions

2. Frontend Display:
   - Real-time updates via Socket.IO events
   - Automatic reconnection handling
   - Session persistence across page reloads

### 3. Error Handling

#### Backend Errors
```python
try:
    response = chat_handler.chat(message)
except Exception as e:
    error_response = {
        "status": "error",
        "message": f"Error in chat handler: {str(e)}",
        "session_id": message.get("session_id"),
        "conv_id": message.get("conv_id"),
        "msg_type": "output",
        "content": [],
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "error_type": type(e).__name__
        }
    }
    self.emit("chat", error_response)
```

#### Frontend Error Recovery
- Automatic socket reconnection
- Session state preservation
- Error message display to users

## Performance Optimizations

### Backend
1. Database Optimization
   - Connection pooling
   - Lazy database initialization
   - Session caching

2. Socket.IO Configuration
   - Retry logic for failed emissions
   - Efficient message serialization
   - Error recovery mechanisms

### Frontend
1. UI Optimizations
   - Custom scrollbar styling
   - Overflow handling
   - Keyboard shortcuts

2. State Management
   - Session persistence
   - Efficient DOM updates
   - Automatic reconnection

## Security Considerations

### Data Protection
- All WebSocket communications use secure protocols
- Session validation on both ends
- Error messages sanitized before transmission

## Future Improvements

### Planned Enhancements
1. Backend
   - Enhanced session recovery
   - Better error tracking
   - Performance monitoring

2. Frontend
   - Progressive loading
   - Offline support
   - Enhanced error recovery

### Monitoring
- Add detailed logging
- Implement performance metrics
- Track error rates and types

## Supabase Integration and Data Flow

### Database Schema and Relationships
```typescript
interface Tables {
  videos: {
    id: UUID;                  // Primary key
    video_id: string;          // External video identifier
    collection_id: string;     // Collection grouping
    metadata: JSON;            // Additional video metadata
    created_at: Timestamp;
  };
  
  transcripts: {
    id: UUID;                  // Primary key
    video_id: UUID;            // References videos(id)
    full_text: string;         // Complete transcript
    metadata: JSON;            // Processing metadata
    created_at: Timestamp;
  };
  
  transcript_chunks: {
    id: UUID;                  // Primary key
    transcript_id: UUID;       // References transcripts(id)
    chunk_text: string;        // Text segment
    chunk_index: number;       // Order in transcript
    embedding: vector(1536);   // OpenAI embedding
    metadata: JSON;            // Chunk metadata
    created_at: Timestamp;
  };
  
  generated_outputs: {
    id: UUID;                  // Primary key
    video_id: UUID;           // References videos(id)
    output_type: string;      // e.g., 'sales_prompt', 'voice_prompt'
    content: string;          // Generated content
    metadata: JSON;           // Generation metadata
    created_at: Timestamp;
  };
}
```

### Data Flow Stages

1. **Video Processing**
   - Frontend initiates video selection
   - Backend creates video entry in `videos` table
   - Unique UUID generated for video tracking

2. **Transcript Processing**
   - Video transcribed and stored in `transcripts` table
   - Text split into chunks for embedding
   - Embeddings stored in `transcript_chunks` table
   - Vector similarity search enabled for content retrieval

3. **Content Generation**
   - Agents process video and generate content
   - Results stored in `generated_outputs` table
   - Real-time updates sent via Socket.IO
   - Frontend displays results in appropriate components

4. **Error Recovery**
   - Failed operations logged with metadata
   - Automatic retry for failed database operations
   - Session state preserved for recovery
   - Frontend displays appropriate error states

### Environment Configuration
```env
# Standardized Supabase Variables
SUPABASE_PROJECT_REF=<project_reference>    # Project reference for URL construction
SUPABASE_ANON_KEY=<anon_key>               # Anonymous client key
```

## Edge Functions Integration

### Synchronous Processing Flow
The Edge Functions integration follows a synchronous request-response pattern:

1. **Initial Request**
   - Frontend initiates video analysis request
   - Backend validates video data
   - Creates entries in Supabase tables

2. **Edge Function Processing**
   ```typescript
   interface EdgeFunctionResponse {
     status: 'success' | 'error';
     data: {
       result: any;
       processing_time: number;
       video_id: UUID;        // Reference to videos table
       output_type: string;   // Type of generated content
     };
     error?: {
       message: string;
       code: string;
       metadata?: any;
     };
   }
   ```

3. **Data Flow Stages**
   - Transcript Processing → Embeddings Generation
   - Content Analysis → Structured Data Extraction
   - Voice Prompt Generation
   - Each stage updates Supabase tables with results
   - Real-time progress updates via Socket.IO

4. **Response Handling**
   - Results stored in `generated_outputs` table
   - Frontend subscribes to updates via Socket.IO
   - UI components render based on output_type
   - Error states handled with fallback displays

5. **Error Management**
   - Detailed error logging with stack traces
   - Failed operations tracked in metadata
   - Automatic retry for transient failures
   - User-friendly error messages in UI 

## Sales Analysis Flow

### Components
1. **SalesPromptExtractorAgent**
   - Entry point for sales analysis requests
   - Manages session state and video transcription
   - Coordinates with SalesAnalysisTool

2. **SalesAnalysisTool**
   - Core analysis engine
   - Generates three outputs:
     - Raw analysis (markdown)
     - Structured data (JSON)
     - Voice prompt (text)

### Data Flow
1. User initiates analysis with `@sales_prompt_extractor`
2. Agent validates video_id and collection_id
3. Video is transcribed if needed
4. Transcript is processed by SalesAnalysisTool
5. Results are stored in:
   - Supabase vector store
   - Local SQLite database
   - Generated outputs table
6. Formatted results are returned via socket.io

### Output Format
The system returns a unified response containing:
```markdown
## Analysis
```markdown
[Detailed analysis text]
```

## Structured Data
```json
{
  "analysis_data": {...}
}
```

## Voice Prompt
```
[Voice agent instructions]
```

## Training Data
```json
{
  "examples": [
    {
      "input": "Question or prompt based on transcript",
      "output": "Appropriate response from transcript"
    },
    ...
  ]
}
```

This format ensures consistent display and easy parsing of results.

### Training Data Flow
1. **Extraction Process**
   - Transcript is processed by LLM with specialized prompt
   - Examples are extracted using regex pattern matching
   - Each example contains input-output pairs
   - Examples are validated for completeness

2. **Storage**
   - Training data stored in `generated_outputs` table
   - JSONB column allows efficient querying
   - GIN index optimizes search performance
   - Examples linked to original video and collection

3. **Retrieval**
   - Training data accessed via vector store
   - Examples can be filtered by video or collection
   - Format optimized for LLM fine-tuning
   - Cached for improved performance

4. **Quality Control**
   - Examples validated for completeness
   - Personal information removed
   - Context preserved for each example
   - Diverse example types maintained 