# LLM-Optimized Output Formats

## Current & Proposed Output Formats

### 1. Conversation Maps (JSON)
```json
{
  "conversation_flow": {
    "nodes": [
      {
        "id": "opening_1",
        "type": "sales_opener",
        "content": "Permission-based greeting",
        "examples": ["Would you mind if I took 30 seconds of your time?"],
        "success_metrics": {
          "response_rate": 0.85,
          "positive_sentiment": 0.92
        }
      }
    ],
    "edges": [
      {
        "from": "opening_1",
        "to": "value_prop_1",
        "conditions": ["positive_response", "customer_engaged"],
        "fallback": "soft_close_1"
      }
    ]
  }
}
```

### 2. Technique Classification Dataset (JSONL)
```jsonl
{"text": "Would you mind if I shared something concerning?", "technique": "permission_based", "context": "opening", "effectiveness": 0.89}
{"text": "I understand you need to think about it. What specific aspects are you considering?", "technique": "objection_handling", "context": "closing", "effectiveness": 0.76}
```

### 3. Few-Shot Learning Prompts (YAML)
```yaml
few_shot_examples:
  - context: "Customer mentions budget concerns"
    input: "I need to think about the price."
    response: "I completely understand. To help you make an informed decision, could I break down the monthly investment for you?"
    reasoning: "Acknowledges concern, offers specific solution, reframes as investment"
    
  - context: "Customer shows interest but hesitates"
    input: "This sounds good, but I need to talk to my partner."
    response: "That makes perfect sense. What specific aspects would you like me to clarify for when you discuss this with them?"
    reasoning: "Validates decision process, offers helpful information, maintains engagement"
```

### 4. Semantic Role Templates (JSON)
```json
{
  "sales_patterns": [
    {
      "pattern_type": "value_proposition",
      "structure": {
        "benefit": {"type": "string", "position": "leading"},
        "social_proof": {"type": "string", "optional": true},
        "call_to_action": {"type": "string", "position": "closing"}
      },
      "examples": [
        {
          "benefit": "This system pays for itself in energy savings",
          "social_proof": "Just like our customer John who saved $200 monthly",
          "call_to_action": "Would you like to see your potential savings?"
        }
      ]
    }
  ]
}
```

### 5. Contextual State Transitions (YAML)
```yaml
state_transitions:
  - current_state: "initial_contact"
    customer_signal: "shows_interest"
    next_states:
      primary: "value_presentation"
      fallback: "rapport_building"
    context_variables:
      interest_level: float
      objection_count: int
      engagement_signals: list[str]
    
  - current_state: "value_presentation"
    customer_signal: "price_objection"
    next_states:
      primary: "value_justification"
      fallback: "soft_close"
```

### 6. Embeddings with Metadata (JSON)
```json
{
  "embedding_vectors": [
    {
      "text": "Original sales dialogue segment",
      "embedding": [...],  # 1536-dimensional vector
      "metadata": {
        "technique_type": "value_proposition",
        "effectiveness_score": 0.87,
        "customer_response": "positive",
        "context_tags": ["budget_discussion", "feature_explanation"],
        "sequential_position": {
          "relative_position": 0.25,
          "conversation_phase": "discovery"
        }
      }
    }
  ]
}
```

### 7. Conversation Tree Training Data (JSON)
```json
{
  "dialogue_trees": [
    {
      "root": {
        "speaker": "agent",
        "text": "Initial greeting",
        "children": [
          {
            "speaker": "customer",
            "intent": "positive_response",
            "text": "Customer shows interest",
            "children": []
          },
          {
            "speaker": "customer",
            "intent": "objection",
            "text": "Customer raises concern",
            "children": []
          }
        ]
      },
      "metadata": {
        "success_path": ["root", "positive_response", "value_proposition"],
        "conversion_rate": 0.72
      }
    }
  ]
}
```

## Implementation Notes

### Storage Considerations
- Use JSONB columns in Supabase for flexible schema evolution
- Implement GIN indexing for efficient querying
- Store embeddings in dedicated vector columns

### Retrieval Optimization
```sql
CREATE INDEX idx_conversation_embedding ON transcript_chunks 
USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);
```

### Integration Points
1. **Data Collection**
   - Capture during live conversations
   - Extract from recorded sessions
   - Generate from synthetic data

2. **Quality Control**
   - Validate format consistency
   - Check for completeness
   - Verify semantic correctness

3. **Usage Patterns**
   - Fine-tuning datasets
   - Few-shot learning examples
   - Retrieval-augmented generation

## Recommended Updates to Data Flow

1. Add new table for optimized LLM formats:
```sql
CREATE TABLE llm_training_data (
    id UUID PRIMARY KEY,
    video_id UUID REFERENCES videos(id),
    format_type TEXT,
    content JSONB,
    embedding vector(1536),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, now())
);
```

2. Update Socket.IO events to include new formats:
```typescript
interface LLMTrainingMessage {
    session_id: string;
    format_type: string;
    content: any;
    metadata: {
        timestamp: string;
        format_version: string;
        quality_metrics: Record<string, number>;
    }
}
```

3. Implement parallel processing for format generation:
```python
async def generate_llm_formats(transcript: str):
    tasks = [
        generate_conversation_map(transcript),
        generate_technique_dataset(transcript),
        generate_few_shot_prompts(transcript),
        # ... other format generators
    ]
    return await asyncio.gather(*tasks)
``` 