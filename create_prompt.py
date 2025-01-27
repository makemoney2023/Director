import requests

headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer sk-vqlxa51t2rw3av0i45lrke7p6jnfl7ciqm7qy12gh3hngipnbdkhyzrfylpy58f969'}

prompt_data = {'prompt': 'Hello! As your AI assistant, I will help you navigate through sales conversations.', 'name': 'Sales Voice Prompt', 'description': 'Voice prompt for sales pathway'}

response = requests.post('https://api.bland.ai/v1/prompts', headers=headers, json=prompt_data)
print('Response:', response.text)
