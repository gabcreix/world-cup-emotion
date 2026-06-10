"""
Scraper para NewsNow — la fuente no expone un feed RSS funcional
(la URL `?type=ts.rss` devuelve la página HTML normal, una SPA en Vue.js
sin contenido renderizado en el servidor).

Reutiliza el driver de undetected-chromedriver (igual que fbref_squads)
para renderizar la página con JS y extraer los enlaces de titulares
del DOM resultante.
"""

import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from world_cup.pipelines.fbref_squads.bronze import _create_driver

NEWSNOW_URL = "https://www.newsnow.co.uk/h/Sport/Football/International/2026+FIFA+World+Cup"
PAGE_WAIT = 8.0
MIN_TITLE_LEN = 20

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Dominios a ignorar: el sitio principal de NewsNow, redes sociales,
# ad-tech/tracking. Nota: c.newsnow.co.uk es el dominio de redirección
# de los enlaces de titulares y NO debe ignorarse.
_IGNORED_DOMAINS = (
    "www.newsnow.co.uk",
    "newsnow.co.uk",
    "criteo.com",
    "doubleclick.net",
    "googlesyndication.com",
    "google.com",
    "googleadservices.com",
    "adnxs.com",
    "blismedia.com",
    "opera.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "dockside.io",
    "amazon-adsystem.com",
)


def _extract_entries(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")

    seen_urls: set[str] = set()
    entries: list[dict] = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.startswith("http"):
            continue
        if urlparse(href).netloc in _IGNORED_DOMAINS:
            continue

        title = a.get_text(" ", strip=True)
        if len(title) < MIN_TITLE_LEN:
            continue

        if href in seen_urls:
            continue
        seen_urls.add(href)

        entries.append({"title": title, "link": href})

    return entries


def _resolve_redirect(url: str) -> str:
    """Sigue la redirección de c.newsnow.co.uk y devuelve la URL final del artículo."""
    try:
        resp = requests.head(
            url, headers={"User-Agent": USER_AGENT}, allow_redirects=True, timeout=10
        )
        if resp.url and resp.url != url:
            return resp.url

        # Algunos servidores no soportan HEAD correctamente: probar con GET
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, allow_redirects=True,
            timeout=10, stream=True,
        )
        resp.close()
        return resp.url
    except requests.RequestException:
        return url


def fetch_entries() -> list[dict]:
    """Renderiza la página de NewsNow con Selenium y devuelve titulares crudos."""
    print("[INFO] Iniciando Chrome (undetected) para NewsNow...")
    driver = _create_driver()
    try:
        driver.get(NEWSNOW_URL)
        time.sleep(PAGE_WAIT)
        html = driver.page_source
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    entries = _extract_entries(html)

    for entry in entries:
        entry["link"] = _resolve_redirect(entry["link"])

    return entries


if __name__ == "__main__":
    for entry in fetch_entries():
        print(entry)
