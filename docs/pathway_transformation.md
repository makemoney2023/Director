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

### Enhanced GPT-4 Prompt for Pathway Generation

```
You are an expert conversation designer for AI voice agents. Analyze the following conversation prompts and create a structured pathway that maximizes conversational intelligence and natural flow.

For each conversation node:

1. Generate a semantic name that captures:
   - The primary intent (e.g., "Value Discovery", "Objection Resolution")
   - The conversation phase (e.g., "Initial Engagement", "Deep Dive")
   - The expected outcome (e.g., "Interest Qualification", "Commitment Securing")

2. Create edge labels that represent:
   - User's emotional state ("Interest Piqued", "Concern Expressed")
   - Decision points ("Ready to Proceed", "Needs More Information")
   - Conversation shifts ("Topic Transition", "Depth Request")

3. For each node, specify:
   {
     "name": "Semantic name capturing intent",
     "type": "Node type (Default/End Call/Transfer/etc)",
     "data": {
       "prompt": "The actual conversation text",
       "intent": "Primary conversational goal",
       "success_condition": "What indicates successful execution",
       "failure_condition": "What triggers alternative paths",
       "expected_outcomes": ["Possible next states"],
       "transition_triggers": ["Specific phrases or sentiments that trigger transitions"]
     }
   }

4. For each edge, specify:
   {
     "label": "Clear transition state",
     "condition": "Specific condition triggering this path",
     "description": "Detailed context for this transition",
     "user_signals": ["Indicators that validate this path"]
   }

Required Node Types:
1. Engagement Nodes (Starting conversations)
2. Discovery Nodes (Understanding needs)
3. Value Proposition Nodes (Presenting solutions)
4. Objection Handler Nodes (Addressing concerns)
5. Decision Nodes (Securing next steps)
6. Transfer Nodes (Escalating to humans)
7. Closing Nodes (Ending conversations)

Edge Requirements:
- Must connect logically related nodes
- Should include both positive and negative paths
- Must handle unexpected user states
- Should support dynamic path selection

Example Node Name Transformations:
❌ "Handle Objection" → ✅ "Budget Constraint Resolution"
❌ "Continue Discussion" → ✅ "Value Alignment Exploration"
❌ "Transfer Call" → ✅ "Technical Expertise Escalation"

Example Edge Label Transformations:
❌ "Continue" → ✅ "Value Proposition Accepted"
❌ "Transfer" → ✅ "Complex Requirements Detected"
❌ "End Call" → ✅ "Successful Commitment Secured"

The pathway should demonstrate:
1. Natural conversation flow
2. Intelligent handling of context
3. Appropriate escalation points
4. Clear success/failure conditions
5. Semantic clarity in all names and labels

Format your response as a JSON structure containing:
1. Nodes array with semantic names and full metadata
2. Edges array with meaningful transition labels
3. Global handlers for universal states
4. Entry and exit points clearly marked

Consider the conversation context and ensure all transitions feel natural and user-centric.
```

### Example Output Structure:
```json
{
  "nodes": [
    {
      "id": "value_discovery_initial",
      "name": "Initial Value Discovery",
      "type": "Default",
      "data": {
        "prompt": "...",
        "intent": "Establish value alignment",
        "success_condition": "User expresses interest in specific benefits",
        "failure_condition": "User shows immediate resistance",
        "expected_outcomes": [
          "value_interest_expressed",
          "immediate_objection_raised",
          "more_information_requested"
        ]
      }
    }
  ],
  "edges": [
    {
      "source": "value_discovery_initial",
      "target": "benefit_exploration",
      "label": "Value Interest Expressed",
      "condition": "User shows interest in specific benefits",
      "description": "Transition to detailed benefit discussion",
      "user_signals": [
        "Asks for more details",
        "Expresses positive acknowledgment",
        "Shares relevant challenge"
      ]
    }
  ]
}
```

### Next Steps

1. Implement consistent start node creation
2. Ensure proper end node handling
3. Enhance edge descriptions and conditions
4. Add comprehensive global handlers
5. Improve position calculation for better visualization 