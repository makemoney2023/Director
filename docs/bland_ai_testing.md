# Bland AI Integration Testing Guide

## Overview
This guide documents the process for testing the Bland AI integration, including retrieving prompts and updating conversation pathways using Python scripts.

## Prerequisites
- Python 3.x installed
- `requests` library (`pip install requests`)
- Bland AI API key
- Access to the Bland AI dashboard

## Authentication
The Bland AI API key should be included in the Authorization header:
```python
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_BLAND_AI_API_KEY"
}
```

## Testing Scripts

### 1. List All Prompts
```python
import requests

headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_BLAND_AI_API_KEY"
}

response = requests.get("https://api.bland.ai/v1/prompts", headers=headers)
prompts = response.json()["prompts"]
```

### 2. Update Pathway with Prompt
```python
import requests

# Headers setup
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_BLAND_AI_API_KEY"
}

# Get prompt content
r = requests.get("https://api.bland.ai/v1/prompts", headers=headers)
prompt = next((p for p in r.json()["prompts"] if p["id"] == "YOUR_PROMPT_ID"), None)

# Prepare pathway data
data = {
    "name": "Pathway Name",
    "description": "Pathway Description",
    "nodes": [
        {
            "id": "1",
            "data": {
                "name": "Start",
                "text": "Hey there, how are you doing today?",
                "isStart": True
            },
            "type": "Default"
        },
        {
            "id": "custom_node_id",
            "data": {
                "name": "Node Name",
                "text": prompt["prompt"],
                "tools": [prompt["id"]],
                "prompt_id": prompt["id"],
                "prompt": prompt["prompt"]
            },
            "type": "Knowledge Base"
        }
    ],
    "edges": [
        {
            "id": "edge-1",
            "source": "1",
            "target": "custom_node_id",
            "label": "edge_label"
        }
    ]
}

# Update pathway
response = requests.post(
    "https://api.bland.ai/v1/convo_pathway/YOUR_PATHWAY_ID",
    headers=headers,
    json=data
)
```

## Testing Process
1. First, list all prompts to get the correct prompt ID
2. Note the prompt ID you want to use
3. Create a Python script with the above code
4. Replace placeholder values:
   - YOUR_BLAND_AI_API_KEY
   - YOUR_PROMPT_ID
   - YOUR_PATHWAY_ID
   - Customize node names and structure as needed
5. Run the script and check the response
6. Verify the changes in the Bland AI dashboard

## Common Issues and Solutions
1. If you get a 404 error, verify the pathway ID and endpoint URL
2. If you get a TypeError with NoneType, ensure the prompt ID exists
3. For large prompts, ensure you're using UTF-8 encoding in your Python script

## Example Usage
```powershell
# Create and run the script
echo 'import requests...' | Out-File -FilePath update_pathway.py -Encoding utf8
python update_pathway.py
```

## Successful Response
A successful update will return:
```json
{
    "status": "success",
    "message": "Pathway updated successfully",
    "pathway_data": {
        // Pathway details
    }
}
```

## Advanced Use Cases

### Creating a Pathway from Multiple Supabase Prompts
```python
import requests
import json

# Headers setup
supabase_headers = {
    "apikey": "YOUR_SUPABASE_ANON_KEY",
    "Authorization": "Bearer YOUR_SUPABASE_ANON_KEY"
}

bland_headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_BLAND_AI_API_KEY"
}

# 1. Get last 5 voice prompts from Supabase
supabase_url = "https://YOUR_PROJECT_ID.supabase.co/rest/v1/generated_outputs"
query_params = {
    "select": "*",
    "output_type": "eq.voice_prompt",
    "order": "created_at.desc",
    "limit": "5"
}

response = requests.get(
    supabase_url,
    headers=supabase_headers,
    params=query_params
)
voice_prompts = response.json()

# 2. Create nodes for each prompt
nodes = [
    {
        "id": "1",
        "data": {
            "name": "Start",
            "text": "Welcome! Let's begin the conversation.",
            "isStart": True
        },
        "type": "Default"
    }
]

edges = []

# Add nodes for each prompt
for i, prompt in enumerate(voice_prompts, start=1):
    node_id = f"prompt_node_{i}"
    nodes.append({
        "id": node_id,
        "data": {
            "name": f"Voice Prompt {i}",
            "text": prompt["output_content"],
            "type": "Knowledge Base"
        },
        "type": "Knowledge Base",
        "position": {"x": 0, "y": i * 100}  # Stack nodes vertically
    })
    
    # Connect to previous node
    source = "1" if i == 1 else f"prompt_node_{i-1}"
    edges.append({
        "id": f"edge_{i}",
        "source": source,
        "target": node_id,
        "label": f"next_prompt_{i}"
    })

# 3. Create pathway data
pathway_data = {
    "name": "Voice Prompts Pathway",
    "description": "Pathway containing last 5 voice prompts from Supabase",
    "nodes": nodes,
    "edges": edges
}

# 4. Create new pathway
bland_url = "https://api.bland.ai/v1/convo_pathway"
response = requests.post(
    bland_url,
    headers=bland_headers,
    json=pathway_data
)

print(json.dumps(response.json(), indent=2))
```

### PowerShell Usage
```powershell
# Create the script with proper encoding
$script = @'
[PASTE PYTHON SCRIPT HERE]
'@

# Save to file with UTF-8 encoding
$script | Out-File -FilePath create_pathway.py -Encoding utf8

# Run the script
python create_pathway.py
```

### Required Environment Variables
```bash
SUPABASE_PROJECT_ID=your_project_id
SUPABASE_ANON_KEY=your_anon_key
BLAND_AI_API_KEY=your_bland_ai_key
```

### Expected Response
```json
{
    "status": "success",
    "message": "Pathway created successfully",
    "pathway_data": {
        "id": "new-pathway-id",
        "name": "Voice Prompts Pathway",
        "nodes": [...],
        "edges": [...]
    }
}
```

### Common Issues
1. If Supabase query fails, verify your project ID and anon key
2. For large prompts, ensure proper encoding in the script
3. If nodes aren't visible in UI, check the position coordinates
4. Verify that all node IDs are unique within the pathway 