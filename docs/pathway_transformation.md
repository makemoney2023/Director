## Pathway Transformation Process

### Overview
The pathway transformation process converts generated outputs (voice prompts) into a structured Bland AI conversation pathway. This document outlines the current implementation and areas for improvement.

### Current Implementation

#### Key Components:
1. `PathwayStructureTransformer` - Main class handling transformation
2. `SalesPathwayTransformer` - Specialized transformer for sales pathways
3. `_generate_structured_pathway` - Core method using GPT-4 for structure generation

#### Node Types:
- Default
- End Call
- Transfer Call
- Knowledge Base
- Webhook
- Global

#### Required Node Structure:
```json
{
  "id": "unique_id",
  "type": "node_type",
  "data": {
    "name": "Node Name",
    "active": false,
    "prompt": "Node prompt text",
    "condition": "Condition for proceeding",
    "globalPrompt": "Global context prompt",
    "modelOptions": {
      "modelType": "smart",
      "temperature": 0.2,
      "skipUserResponse": false,
      "block_interruptions": false
    }
  },
  "width": 320,
  "height": 127,
  "position": {"x": 0, "y": 0},
  "dragging": false,
  "selected": false
}
```

### Current GPT-4 Prompt for Structure Generation
```
Generate a structured node name (2-4 words) for a conversation node based on its prompt. The name should capture the main intent or action of the prompt.
```

### Areas for Improvement

1. **Start Node Requirements**
   - Must be first node in pathway
   - Should have isStart: true
   - Should establish conversation context
   - Currently not consistently implemented

2. **End Node Requirements**
   - Must have type: "End Call"
   - Should properly close conversation
   - Multiple end scenarios needed
   - Currently missing in some pathways

3. **Edge Requirements**
   - Need descriptive labels
   - Should include conditions
   - Better handling of branching logic

4. **Global Node Handling**
   - Frustration handlers
   - Transfer scenarios
   - Error recovery

### Proposed Enhanced GPT-4 Prompt

```
You are designing a conversation pathway for an AI voice agent. Given the following voice prompts, create a structured conversation flow that includes:

1. A clear start node that:
   - Introduces the agent and purpose
   - Establishes initial context
   - Has isStart: true

2. Main conversation nodes that:
   - Have clear, descriptive names (2-4 words)
   - Include specific prompts and conditions
   - Handle user responses appropriately

3. End nodes for different scenarios:
   - Successful completion
   - User rejection
   - Transfer to human
   - Error handling

4. Global handlers for:
   - User frustration
   - Common objections
   - Technical issues

Each node should specify:
- Type (Default/End Call/Transfer/etc)
- Name
- Prompt
- Condition for proceeding
- Model options
- Position in flow

Each edge should specify:
- Source and target nodes
- Transition condition
- Description of flow

The pathway should handle:
- Multiple conversation paths
- Graceful error recovery
- Clear exit points
- Smooth transitions

Format the response as a structured JSON with nodes and edges arrays.
```

### Next Steps

1. Implement consistent start node creation
2. Ensure proper end node handling
3. Enhance edge descriptions and conditions
4. Add comprehensive global handlers
5. Improve position calculation for better visualization 