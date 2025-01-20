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

## Edge Functions Integration

### Synchronous Processing Flow
The Edge Functions integration follows a synchronous request-response pattern:

1. **Initial Request**
   - Frontend initiates video analysis request
   - Backend processes transcript and embeddings
   - Direct synchronous calls to Edge Functions

2. **Edge Function Processing**
   ```typescript
   interface EdgeFunctionResponse {
     status: 'success' | 'error';
     data: {
       result: any;
       processing_time: number;
     };
     error?: {
       message: string;
       code: string;
     };
   }
   ```

3. **Data Flow Stages**
   - Transcript Processing → Embeddings → Structured Data → Voice Prompt
   - Each stage waits for completion before proceeding
   - Results stored in Supabase tables for persistence

4. **Response Handling**
   - Backend aggregates results from all stages
   - Returns complete analysis to frontend
   - Frontend updates UI with all data simultaneously

5. **Error Management**
   - Immediate error reporting from Edge Functions
   - Backend handles errors and returns appropriate response
   - No automatic retries (managed by backend if needed)

### Integration with Existing Flow
- Edge Functions extend the existing chat handler functionality
- Maintains compatibility with current WebSocket architecture
- Preserves session management and error recovery mechanisms 