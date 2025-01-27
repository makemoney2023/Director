import requests

bland_headers = {'Authorization': 'Bearer sk-vqlxa51t2rw3av0i45lrke7p6jnfl7ciqm7qy12gh3hngipnbdkhyzrfylpy58f969'}

prompt = {'name': 'Sales Guide 1', 'prompt': 'Hello! As your AI assistant, I\'m going to help you navigate through sales conversations with confidence and strategy.'}

r = requests.post('https://api.bland.ai/v1/prompts', headers=bland_headers, json=prompt)
print(r.json())
