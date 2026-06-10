"""
Debug: renderiza NewsNow con Selenium, guarda el HTML y analiza los <a href>
para entender por qué el scraper no encuentra titulares.

Uso: python debug_newsnow2.py
"""

import time
from collections import Counter
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from world_cup.pipelines.fbref_squads.bronze import _create_driver
from world_cup.pipelines.news_rss.scrape_newsnow import NEWSNOW_URL, PAGE_WAIT

print("[INFO] Iniciando Chrome...")
driver = _create_driver()
try:
    driver.get(NEWSNOW_URL)
    print(f"[INFO] Esperando {PAGE_WAIT}s...")
    time.sleep(PAGE_WAIT)
    print(f"[INFO] title={driver.title!r}")
    html = driver.page_source
finally:
    driver.quit()

with open("newsnow_rendered.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"[INFO] HTML guardado: newsnow_rendered.html ({len(html)} chars)")

soup = BeautifulSoup(html, "lxml")
all_links = soup.find_all("a", href=True)
print(f"\n[INFO] Total <a href>: {len(all_links)}")

http_links = [a for a in all_links if a["href"].strip().startswith("http")]
print(f"[INFO] <a href> que empiezan por http: {len(http_links)}")

domains = Counter()
for a in http_links:
    domain = urlparse(a["href"]).netloc
    domains[domain] += 1

print("\n[INFO] Dominios más frecuentes:")
for domain, count in domains.most_common(20):
    print(f"  {count:4d}  {domain}")

print("\n[INFO] Primeros 30 <a href> http con su texto (longitud y contenido):")
for a in http_links[:30]:
    text = a.get_text(" ", strip=True)
    print(f"  len={len(text):3d}  href={a['href'][:80]!r}  text={text[:80]!r}")
