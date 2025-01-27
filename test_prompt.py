import requests

headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer sk-vqlxa51t2rw3av0i45lrke7p6jnfl7ciqm7qy12gh3hngipnbdkhyzrfylpy58f969'}

# Test creating a single prompt
prompt_data = {'prompt': 'Hello! As your AI assistant, I will help you navigate through sales conversations.', 'name': 'Test Voice Prompt', 'description': 'Test prompt creation'}

response = requests.post('https://api.bland.ai/v1/prompt', headers=headers, json=prompt_data)
print('Response:', response.text)

