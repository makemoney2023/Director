import requests
import json

supabase_url = 'https://pzzxahvrgvwmrfbxqsxg.supabase.co'
supabase_key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB6enhhaHZyZ3Z3bXJmYnhxc3hnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MDg2NDQ3OTUsImV4cCI6MjAyNDIyMDc5NX0.YkPd8178xKiR0XCQjZ-LJh0PhPLR0DvHGCf0gqvBHvM'

headers = {
    'apikey': supabase_key,
    'Authorization': f'Bearer {supabase_key}'
}

response = requests.get(
    f'{supabase_url}/rest/v1/generated_outputs',
    headers=headers,
    params={
        'select': '*',
        'output_type': 'eq.voice_prompt',
        'order': 'created_at.desc'
    }
)

prompts = response.json()
with open('voice_prompts.json', 'w') as f:
    json.dump(prompts, f, indent=2)

print(f'Found {len(prompts)} voice prompts. Saved to voice_prompts.json')
