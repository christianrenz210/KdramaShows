import requests, json, re

KISSKH_BASE = 'https://kisskh.nl'

r = requests.get(f'{KISSKH_BASE}/api/DramaList/Search?q=Spider-Man', timeout=15)
data = r.json()
for item in data:
    print(f'ID={item["id"]} Title={item["title"]}')

r2 = requests.get(f'{KISSKH_BASE}/api/DramaList/Drama/6653?isq=false', timeout=15)
drama = r2.json()
print('Title:', drama.get('title'))
print('Type:', drama.get('type'))
for ep in drama.get('episodes', []):
    print(f'  Ep {ep["number"]}: id={ep["id"]}')
