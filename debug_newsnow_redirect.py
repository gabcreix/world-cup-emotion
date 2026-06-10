"""
Debug: inspecciona qué devuelve realmente c.newsnow.co.uk/A/... al
seguir un enlace de titular, para ver si la redirección es HTTP
(Location header) o vía JS/meta-refresh.

Uso: python debug_newsnow_redirect.py
"""

import requests

from world_cup.pipelines.news_rss.scrape_newsnow import USER_AGENT, fetch_entries

print("[INFO] Obteniendo titulares de NewsNow (esto abre Chrome)...")
# Para no repetir el scraping completo, usa una URL de ejemplo fija si ya tienes una.
# Si prefieres usar una real, descomenta la línea siguiente:
entries_raw = None

# URL de ejemplo (sustituye por una real de tu última ejecución si quieres)
test_url = "https://c.newsnow.co.uk/A/1315908127?-58042:28968"

print(f"\n[INFO] Probando: {test_url}")

resp = requests.get(
    test_url,
    headers={"User-Agent": USER_AGENT},
    allow_redirects=True,
    timeout=15,
)
print(f"status: {resp.status_code}")
print(f"final url: {resp.url}")
print(f"history (redirects): {[r.status_code for r in resp.history]}")
for r in resp.history:
    print(f"  {r.status_code} -> {r.headers.get('Location')}")
print(f"content-type: {resp.headers.get('content-type')}")
print(f"\n--- primeros 1000 caracteres del body ---")
print(resp.text[:1000])
