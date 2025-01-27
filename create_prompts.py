import requests
import json

bland_headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer sk-vqlxa51t2rw3av0i45lrke7p6jnfl7ciqm7qy12gh3hngipnbdkhyzrfylpy58f969'}
supabase_headers = {'apikey': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB6enhhaHZyZ3Z3bXJmYnhxc3hnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MDg2NDQ3OTUsImV4cCI6MjAyNDIyMDc5NX0.YkPd8178xKiR0XCQjZ-LJh0PhPLR0DvHGCf0gqvBHvM', 'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB6enhhaHZyZ3Z3bXJmYnhxc3hnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MDg2NDQ3OTUsImV4cCI6MjAyNDIyMDc5NX0.YkPd8178xKiR0XCQjZ-LJh0PhPLR0DvHGCf0gqvBHvM'}

response = requests.get('https://pzzxahvrgvwmrfbxqsxg.supabase.co/rest/v1/generated_outputs', headers=supabase_headers, params={'select': '*', 'output_type': 'eq.voice_prompt', 'order': 'created_at.desc', 'limit': '5'})
voice_prompts = response.json()
print('Found voice prompts:', len(voice_prompts))

for vp in voice_prompts:
    content = json.loads(vp['content'])
    prompt_text = content.get('prompt', '')
    prompt_data = {'prompt': prompt_text, 'name': f'Voice Prompt', 'description': f'Voice prompt from Supabase'}
    r = requests.post('https://api.bland.ai/v1/prompt', headers=bland_headers, json=prompt_data)
    print(f'Created prompt response:', r.text)

