"""
Bronze layer — FBref squads.

Descarga HTML crudo de FBref y lo guarda en data/bronze/fbref_squads/.
No transforma nada: lo que llega de la fuente se persiste tal cual.

Requiere Playwright instalado:
    pip install playwright
    playwright install chromium
"""

import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[5]
BRONZE_DIR = ROOT / "data" / "bronze" / "fbref_squads"

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BASE_URL = "https://fbref.com"
TOURNAMENT_URL = f"{BASE_URL}/en/comps/1/2026/2026-FIFA-World-Cup-Stats"
REQUEST_DELAY = 5.0  # segundos entre requests


# ---------------------------------------------------------------------------
# Helpers Playwright
# ---------------------------------------------------------------------------

def _fetch_html(page, url: str) -> str:
    """Navega a url y devuelve el HTML completo."""
    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    # Esperar a que cargue la tabla principal
    try:
        page.wait_for_selector("table", timeout=10_000)
    except PlaywrightTimeout:
        pass  # continuar aunque no haya tabla visible
    return page.content()


def _get_or_cache(page, url: str, cache_path: Path) -> str:
    """Devuelve HTML desde cache si existe, si no lo descarga y guarda."""
    if cache_path.exists():
        print(f"  [cache] {cache_path.name}")
        return cache_path.read_text(encoding="utf-8")

    print(f"  [fetch] {url}")
    time.sleep(REQUEST_DELAY)
    html = _fetch_html(page, url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(html, encoding="utf-8")
    return html


# ---------------------------------------------------------------------------
# Step B1 — Descubrir URLs de equipos
# ---------------------------------------------------------------------------

def discover_team_urls(page) -> dict[str, str]:
    """
    Extrae los links de plantilla de cada selección desde la página del torneo.
    Devuelve {nombre_equipo: url_plantilla} y lo persiste en bronze.
    """
    from bs4 import BeautifulSoup

    cache_path = BRONZE_DIR / "tournament_page.html"
    html = _get_or_cache(page, TOURNAMENT_URL, cache_path)
    soup = BeautifulSoup(html, "lxml")

    team_urls: dict[str, str] = {}
    for a in soup.select("a[href*='/en/squads/']"):
        href = a["href"]
        name = a.get_text(strip=True)
        if not name:
            continue
        if re.match(r"^/en/squads/[a-f0-9]+/[\w%-]+-Stats$", href):
            if name not in team_urls:
                team_urls[name] = BASE_URL + href

    print(f"\nEquipos encontrados: {len(team_urls)}")
    for name, url in sorted(team_urls.items()):
        print(f"  {name}: {url}")

    # Persistir índice en bronze
    out = BRONZE_DIR / "team_urls.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(team_urls, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Guardado: {out}")

    return team_urls


# ---------------------------------------------------------------------------
# Step B2 — Descargar HTML de plantilla por equipo
# ---------------------------------------------------------------------------

def fetch_squad_html(page, team_name: str, team_url: str) -> str:
    """
    Descarga y cachea el HTML de la página de stats de un equipo.
    Devuelve el HTML crudo.
    """
    safe_name = re.sub(r"[^\w]", "_", team_name)
    cache_path = BRONZE_DIR / "squads" / f"{safe_name}.html"
    return _get_or_cache(page, team_url, cache_path)


def fetch_all_squads(team_urls: dict[str, str]) -> None:
    """
    Descarga HTMLs de todos los equipos usando una sola sesión de Playwright.
    Los guarda en data/bronze/fbref_squads/squads/.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # User-agent de Chrome real
        page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

        for name, url in team_urls.items():
            fetch_squad_html(page, name, url)

        browser.close()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run() -> dict[str, str]:
    """Ejecuta la capa bronze completa. Devuelve el dict team_urls."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
        })

        print("=== BRONZE: Descubriendo URLs de equipos ===")
        team_urls = discover_team_urls(page)

        if not team_urls:
            print("[ERROR] No se encontraron equipos. Revisar URL del torneo.")
            browser.close()
            return {}

        print("\n=== BRONZE: Descargando plantillas ===")
        for name, url in team_urls.items():
            fetch_squad_html(page, name, url)

        browser.close()

    return team_urls


if __name__ == "__main__":
    run()
