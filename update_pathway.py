import requests

headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer sk-vqlxa51t2rw3av0i45lrke7p6jnfl7ciqm7qy12gh3hngipnbdkhyzrfylpy58f969'}

data = {'name': 'Sales Training', 'description': 'Sales training pathway', 'nodes': [{'id': '1', 'data': {'name': 'Start', 'text': 'Hey there!', 'isStart': True}, 'type': 'Default'}, {'id': 'sales_guide_node', 'data': {'name': 'Sales Guide', 'text': 'Using sales training tool', 'tools': ['TL-fc549146-20bc-475b-ae1b-c3c688ee637b'], 'prompt_id': 'PT-29ea182e-c871-4948-8e0a-1705b03e44e2'}, 'type': 'Knowledge Base'}], 'edges': [{'id': 'edge-1', 'source': '1', 'target': 'sales_guide_node', 'label': 'start_sales'}]}

response = requests.post('https://api.bland.ai/v1/convo_pathway/749b4302-92be-4dd0-9c07-591929dac8a6', headers=headers, json=data)
print('Response:', response.text)
