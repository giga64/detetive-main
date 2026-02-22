"""Teste rápido OAB"""
import requests

numero = "5553"
estado = "RN"

url_base = "https://cna.oab.org.br"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
})

print("1. Buscando token...")
resp = session.get(url_base + "/", timeout=15)
print(f"   Status: {resp.status_code}")

import re
csrf_match = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', resp.text)
if csrf_match:
    csrf_token = csrf_match.group(1)
    print(f"   Token: {csrf_token[:20]}...")
else:
    print("   ❌ Não achou token")
    exit(1)

print("\n2. Fazendo busca...")
payload = {
    "NomeAdvo": "",
    "Insc": numero,
    "Uf": estado.upper(),
    "TipoInsc": "1",
    "__RequestVerificationToken": csrf_token,
    "IsMobile": ""
}

resp_search = session.post(url_base + "/Home/Search", data=payload, timeout=15)
print(f"   Status: {resp_search.status_code}")

try:
    search_data = resp_search.json()
    print(f"   Success: {search_data.get('Success')}")
    print(f"   Data: {search_data.get('Data', [])[:1]}")
    
    if search_data.get('Data'):
        resultado = search_data['Data'][0]
        print(f"\n✅ Encontrado!")
        print(f"   Nome: {resultado.get('Nome')}")
        print(f"   Inscrição: {resultado.get('Inscricao')}")
        print(f"   DetailUrl: {resultado.get('DetailUrl')}")
    else:
        print(f"\n❌ Não encontrado")
        print(f"   Message: {search_data.get('ResultMessage')}")
except Exception as e:
    print(f"   ❌ Erro: {e}")
    print(f"   Response: {resp_search.text[:200]}")
