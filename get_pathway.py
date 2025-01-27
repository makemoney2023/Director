import requests

headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer sk-vqlxa51t2rw3av0i45lrke7p6jnfl7ciqm7qy12gh3hngipnbdkhyzrfylpy58f969'}

response = requests.get('https://api.bland.ai/v1/pathway/749b4302-92be-4dd0-9c07-591929dac8a6', headers=headers)
print('Response:', response.text)
