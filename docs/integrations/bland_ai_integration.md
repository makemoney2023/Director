# Bland AI Integration Documentation

## Overview
This document outlines the integration between Director's Sales Prompt Extractor and Bland AI's Conversational Pathways system, enabling automated voice agent generation from analyzed sales conversations.

## Architecture

### High-Level System Flow
```mermaid
graph TD
    A[Sales Recording] --> B[Director Analysis]
    B --> C[Sales Prompt Extractor]
    C --> D[Data Transformation Layer]
    D --> E[Bland AI Pathway Generator]
    E --> F[Voice Agent Deployment]
    
    subgraph Director Platform
    B
    C
    D
    end
    
    subgraph Bland AI Platform
    E
    F
    end
```

### Data Transformation Flow
```mermaid
graph LR
    A[Sales Analysis] --> B[Node Generator]
    A --> C[Edge Generator]
    B --> D[Pathway Constructor]
    C --> D
    D --> E[Bland AI API]
    
    subgraph Data Processors
    B
    C
    D
    end
```

## Data Structure Mapping

### Input Structure (Director)
```mermaid
classDiagram
    class SalesAnalysis {
        +String summary
        +SalesTechnique[] techniques
        +CommunicationStrategy[] strategies
        +ObjectionHandling[] objections
        +TrainingPair[] pairs
        +String[] voicePrompts
    }
    
    class SalesTechnique {
        +String name
        +String description
        +String[] examples
        +String effectiveness
    }
    
    class TrainingPair {
        +String input
        +String output
        +String context
        +Number qualityScore
    }
```

### Output Structure (Bland AI)
```mermaid
classDiagram
    class Pathway {
        +String name
        +String description
        +Node[] nodes
        +Edge[] edges
    }
    
    class Node {
        +String id
        +NodeData data
        +String type
    }
    
    class NodeData {
        +String name
        +Boolean isStart
        +String text
        +String prompt
        +String[] dialogueExamples
        +ModelOptions options
    }
    
    class Edge {
        +String id
        +String source
        +String target
        +String label
    }
```

## Mapping Details

### Node Type Mappings
```mermaid
graph LR
    A[Opening/Greeting] --> B[Start Node]
    C[Sales Technique] --> D[Default Node]
    E[Objection Handling] --> F[Decision Node]
    G[Call Conclusion] --> H[End Call Node]
    I[Transfer Request] --> J[Transfer Node]
```

### Example Pathway Generation
```mermaid
graph TD
    A[Start Node: Greeting] --> B[Technique: Value Proposition]
    B --> C{Decision: Customer Interest}
    C -->|Interested| D[Technique: Appointment Setting]
    C -->|Objection| E[Objection Handler]
    E --> F[Technique: Objection Response]
    F --> D
    D --> G[End: Call Conclusion]
```

## API Integration Points

### Bland AI Endpoints
```mermaid
sequenceDiagram
    participant D as Director
    participant B as Bland AI
    
    D->>B: GET /v1/pathway (List Pathways)
    D->>B: POST /v1/convo_pathway (Create Pathway)
    D->>B: POST /v1/convo_pathway/{id} (Update Pathway)
    
    Note over D,B: Authentication via API Key
```

### Error Handling Flow
```mermaid
graph TD
    A[API Request] --> B{Response Check}
    B -->|Success| C[Process Response]
    B -->|Error| D[Error Handler]
    D --> E{Error Type}
    E -->|Auth| F[Refresh Token]
    E -->|Rate Limit| G[Implement Backoff]
    E -->|Validation| H[Log & Alert]
```

## Implementation Considerations

### Security
```mermaid
graph TD
    A[API Keys] --> B[Secure Storage]
    B --> C[Environment Variables]
    D[Request Data] --> E[Sanitization]
    E --> F[API Call]
```

### Performance
```mermaid
graph LR
    A[Batch Processing] --> B[Rate Limiting]
    B --> C[Caching]
    C --> D[Response Optimization]
```

## Future Enhancements
```mermaid
graph TD
    A[Real-time Updates] --> B[Webhook Integration]
    C[Performance Metrics] --> D[Analytics Dashboard]
    E[A/B Testing] --> F[Optimization Engine]
```

## Detailed API Integration Specifications

### Authentication
```typescript
interface AuthConfig {
    apiKey: string;
    headers: {
        'authorization': string;
        'Content-Type': 'application/json';
    }
}

// Environment Configuration
const BLAND_AI_CONFIG = {
    baseUrl: 'https://api.bland.ai',
    version: 'v1',
    apiKey: process.env.BLAND_AI_API_KEY
}
```

### API Endpoints Specification

#### 1. List Pathways
```typescript
// GET /v1/pathway
interface ListPathwaysResponse {
    pathways: Array<{
        pathway_id: string;
        name: string;
        description: string;
        nodes: Node[];
        edges: Edge[];
    }>;
}

async function listPathways(): Promise<ListPathwaysResponse> {
    endpoint: '/v1/pathway'
    method: 'GET'
    headers: AuthConfig.headers
}
```

#### 2. Create Pathway
```typescript
// POST /v1/convo_pathway
interface CreatePathwayRequest {
    name: string;
    description: string;
    nodes: {
        [nodeId: string]: {
            name: string;
            isStart?: boolean;
            type: 'Default' | 'End Call' | 'Transfer Node' | 'Knowledge Base';
            text?: string;
            prompt?: string;
            dialogueExamples?: string[];
            modelOptions?: {
                interruptionThreshold: number;
                temperature: number;
            };
        };
    };
    edges: {
        [edgeId: string]: {
            source: string;
            target: string;
            label: string;
        };
    };
}

interface CreatePathwayResponse {
    pathway_id: string;
    status: 'success' | 'error';
    message: string;
}
```

#### 3. Update Pathway
```typescript
// POST /v1/convo_pathway/{pathway_id}
interface UpdatePathwayRequest extends CreatePathwayRequest {
    pathway_id: string;
}

interface UpdatePathwayResponse {
    status: 'success' | 'error';
    message: string;
    pathway_data: {
        pathway_id: string;
        name: string;
        description: string;
        nodes: Node[];
        edges: Edge[];
    };
}
```

### Error Handling Implementation

```typescript
interface BlandAIError {
    status: number;
    code: string;
    message: string;
}

class BlandAIErrorHandler {
    static async handleError(error: BlandAIError): Promise<void> {
        switch (error.status) {
            case 401:
                // Authentication Error
                await this.handleAuthError(error);
                break;
            case 429:
                // Rate Limit Error
                await this.handleRateLimitError(error);
                break;
            case 400:
                // Validation Error
                await this.handleValidationError(error);
                break;
            default:
                await this.handleGenericError(error);
        }
    }

    private static async handleAuthError(error: BlandAIError): Promise<void> {
        logger.error('Authentication failed:', error);
        // Implement retry with refreshed credentials
        await this.refreshCredentials();
    }

    private static async handleRateLimitError(error: BlandAIError): Promise<void> {
        const backoffTime = this.calculateBackoff(error);
        logger.warn(`Rate limit exceeded. Backing off for ${backoffTime}ms`);
        await this.sleep(backoffTime);
    }

    private static async handleValidationError(error: BlandAIError): Promise<void> {
        logger.error('Validation error:', error);
        // Log detailed validation errors for debugging
        await this.logValidationDetails(error);
    }
}
```

### Request/Response Flow
```mermaid
sequenceDiagram
    participant Client
    participant ErrorHandler
    participant BlandAPI
    participant ResponseHandler

    Client->>BlandAPI: Make API Request
    alt Success
        BlandAPI->>ResponseHandler: Process Response
        ResponseHandler->>Client: Return Formatted Data
    else Error
        BlandAPI->>ErrorHandler: Handle Error
        ErrorHandler->>ErrorHandler: Determine Error Type
        alt Auth Error
            ErrorHandler->>Client: Refresh & Retry
        else Rate Limit
            ErrorHandler->>ErrorHandler: Apply Backoff
            ErrorHandler->>Client: Retry After Delay
        else Validation
            ErrorHandler->>Client: Return Error Details
        end
    end
```

### Rate Limiting Implementation
```typescript
interface RateLimitConfig {
    maxRequests: number;
    windowMs: number;
    backoffMultiplier: number;
}

class RateLimiter {
    private queue: Array<() => Promise<any>> = [];
    private processing: boolean = false;
    private requestCount: number = 0;
    private windowStart: number = Date.now();

    async addToQueue<T>(request: () => Promise<T>): Promise<T> {
        return new Promise((resolve, reject) => {
            this.queue.push(async () => {
                try {
                    const result = await this.executeWithBackoff(request);
                    resolve(result);
                } catch (error) {
                    reject(error);
                }
            });
            this.processQueue();
        });
    }

    private async executeWithBackoff<T>(
        request: () => Promise<T>,
        retryCount: number = 0
    ): Promise<T> {
        try {
            return await request();
        } catch (error) {
            if (error.status === 429 && retryCount < this.config.maxRetries) {
                const backoffTime = this.calculateBackoff(retryCount);
                await this.sleep(backoffTime);
                return this.executeWithBackoff(request, retryCount + 1);
            }
            throw error;
        }
    }
}
```

### Response Caching
```typescript
interface CacheConfig {
    ttl: number;
    maxSize: number;
}

class ResponseCache {
    private cache: Map<string, {
        data: any;
        timestamp: number;
    }> = new Map();

    async get<T>(key: string): Promise<T | null> {
        const cached = this.cache.get(key);
        if (cached && !this.isExpired(cached.timestamp)) {
            return cached.data as T;
        }
        return null;
    }

    set(key: string, data: any): void {
        if (this.cache.size >= this.config.maxSize) {
            this.evictOldest();
        }
        this.cache.set(key, {
            data,
            timestamp: Date.now()
        });
    }
} 