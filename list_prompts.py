import requests

headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer sk-vqlxa51t2rw3av0i45lrke7p6jnfl7ciqm7qy12gh3hngipnbdkhyzrfylpy58f969'}

# Test getting prompts first
response = requests.get('https://api.bland.ai/v1/prompts', headers=headers)
print('Response:', response.text)

