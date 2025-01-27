import requests

headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer sk-vqlxa51t2rw3av0i45lrke7p6jnfl7ciqm7qy12gh3hngipnbdkhyzrfylpy58f969'}

tool_data = {
    'name': 'Sales Training Tool',
    'description': 'Tool for sales training conversations',
    'prompt_id': 'PT-29ea182e-c871-4948-8e0a-1705b03e44e2'
}

response = requests.post('https://api.bland.ai/v1/tools', headers=headers, json=tool_data)
print('Response:', response.text)
