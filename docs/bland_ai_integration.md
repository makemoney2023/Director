# Bland AI Integration

This document describes the integration between Director and Bland AI's conversation pathway system.

## Overview

The Bland AI integration enables creation and management of sophisticated conversation pathways with knowledge base support. It provides a complete interface for:

- Creating and managing conversation pathways
- Integrating knowledge bases with pathways
- Managing voice prompts and responses
- Handling conversation flows and transitions

## Components

### BlandAIService

The `BlandAIService` class provides direct interaction with the Bland AI API. It handles:

- Authentication and request management
- Error handling and response processing
- API endpoint interactions

Key endpoints:

- `GET /v1/pathways` - List all pathways
- `GET /v1/pathways/{id}` - Get pathway details
- `POST /v1/pathways` - Create new pathway
- `PATCH /v1/pathways/{id}` - Update existing pathway
- `POST /v1/prompts` - Store voice prompts
- `POST /v1/knowledgebases` - Create knowledge base
- `GET /v1/knowledgebases` - List knowledge bases
- `GET /v1/knowledgebases/{id}` - Get knowledge base details
- `POST /v1/vectors/query` - Query knowledge base

### BlandAI_Agent

The `BlandAI_Agent` class provides a high-level interface for managing pathways through chat commands. Available commands:

```
@bland_ai <command> [parameters]

Commands:
- list: List all available pathways
- get pathway_id="ID": Get pathway details
- create_empty name="Name" description="Description": Create a new empty pathway
- create name="Name" description="Description" analysis_id="ID": Create pathway from analysis
- update pathway_id="ID" [name="Name"] [description="Description"]: Update pathway
- add_kb pathway_id="ID" kb_id="ID": Add knowledge base to pathway
- remove_kb pathway_id="ID" kb_id="ID": Remove knowledge base from pathway
```

### Knowledge Base Integration

Knowledge bases can be:
- Created from sales analysis data
- Linked to multiple pathways
- Used as tools within conversation nodes
- Queried for relevant information during conversations

## Usage Examples

### Creating a New Pathway

1. Create an empty pathway:
```
@bland_ai create_empty name="Customer Support" description="Basic customer support pathway"
```

2. Create from analysis:
```
@bland_ai create name="Sales Pathway" description="Sales conversation flow" analysis_id="abc123"
```

### Managing Knowledge Bases

1. Add knowledge base to pathway:
```
@bland_ai add_kb pathway_id="path123" kb_id="kb456"
```

2. Remove knowledge base:
```
@bland_ai remove_kb pathway_id="path123" kb_id="kb456"
```

### Viewing Information

1. List all pathways:
```
@bland_ai list
```

2. Get pathway details:
```
@bland_ai get pathway_id="path123"
```

## Error Handling

The integration includes comprehensive error handling:

- API errors are caught and formatted with clear messages
- Network issues are handled gracefully
- Invalid parameters are validated before API calls
- Database errors are logged and reported appropriately

## Configuration

Required environment variables:
- `BLAND_AI_API_KEY`: Your Bland AI API key

## Database Schema

The integration uses the following tables:

### pathway_knowledge_bases
```sql
CREATE TABLE pathway_knowledge_bases (
    pathway_id TEXT NOT NULL,
    kb_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (pathway_id, kb_id)
);
```

### sales_analyses
```sql
CREATE TABLE sales_analyses (
    id TEXT PRIMARY KEY,
    data JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Implementation Notes

1. Knowledge Base Tools
   - Each conversation node can use multiple knowledge bases
   - Knowledge bases are referenced by ID in node tools
   - Queries use vector similarity search

2. Voice Prompts
   - Stored separately from pathways
   - Can be reused across multiple nodes
   - Support dynamic variable substitution

3. Pathway Updates
   - Partial updates are supported
   - Node and edge updates maintain consistency
   - Knowledge base links are preserved

4. Error Recovery
   - Failed operations are rolled back when possible
   - Temporary resources are cleaned up
   - Error states are logged for debugging 