import requests, json
h={"Content-Type":"application/json","Authorization":"Bearer sk-vqlxa51t2rw3av0i45lrke7p6jnfl7ciqm7qy12gh3hngipnbdkhyzrfylpy58f969"}
r=requests.get("https://api.bland.ai/v1/prompts",headers=h)
prompt=next((p for p in r.json()["prompts"] if p["id"]=="PT-333dbe66"),None)
with open("prompt.json","w") as f: json.dump(prompt,f)
