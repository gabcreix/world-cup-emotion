"""
Bronze layer — FBref squads.

Descarga HTML crudo de FBref y lo guarda en data/bronze/fbref_squads/.
No transforma nada: lo que llega de la fuente se persiste tal cual.

Usa undetected-chromedriver para pasar Cloudflare Turnstile.

Requiere:
    pip install undetected-chromedriver beautifulsoup4 lxml
    Chrome instalado en el sistema (usa el Chrome del sistema, no descarga uno nuevo)
"""

import json
import re
import time
from pathlib import Path

import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.webdriver.support.ui import WebDriverWait

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[4]
BRONZE_DIR = ROOT / "data" / "bronze" / "fbref_squads"

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BASE_URL = "https://fbref.com"
TOURNAMENT_URL = f"{BASE_URL}/en/comps/1/2026/2026-FIFA-World-Cup-Stats"
REQUEST_DELAY = 6.0  # segundos entre requests (respetar al servidor)
CF_WAIT = 12.0       # segundos para que Cloudflare resuelva el challenge


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _create_driver() -> uc.Chrome:
    """Crea un Chrome no detectable por Cloudflare."""
    options = uc.ChromeOptions()
    options.add_argument("--lang=en-US")
    options.add_argument("--window-size=1280,900")
    # headless=False es necesario para Cloudflare Turnstile interactivo
    driver = uc.Chrome(options=options, headless=False)
    return driver


def _fetch_html(driver: uc.Chrome, url: str) -> str:
    """
    Navega a url, espera a que Cloudflare resuelva y devuelve el HTML.
    """
    driver.get(url)

    # Esperar a que desaparezca el challenge de Cloudflare
    try:
        WebDriverWait(driver, CF_WAIT).until(
            lambda d: d.title != "Just a moment..."
        )
    except Exception:
        print(f"  [WARN] Posible timeout de Cloudflare para {url}")

    # Espera adicional para que cargue el contenido dinámico
    time.sleep(3)
    return driver.page_source


def _get_or_cache(driver: uc.Chrome, url: str, cache_path: Path) -> str:
    """Devuelve HTML desde cache si existe; si no, lo descarga y guarda."""
    if cache_path.exists():
        content = cache_path.read_text(encoding="utf-8", errors="ignore")
        # Invalidar cache si contiene un challenge no resuelto
        if "Just a moment" in content or "challenge-platform" in content:
            print(f"  [cache-stale] Borrando cache con challenge: {cache_path.name}")
            cache_path.unlink()
        else:
            print(f"  [cache] {cache_path.name}")
            return content

    print(f"  [fetch] {url}")
    time.sleep(REQUEST_DELAY)
    html = _fetch_html(driver, url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(html, encoding="utf-8")
    return html


# ---------------------------------------------------------------------------
# Step B1 — Descubrir URLs de equipos
# ---------------------------------------------------------------------------

def discover_team_urls(driver: uc.Chrome) -> dict[str, str]:
    """
    Extrae los links de plantilla de cada selección desde la página del torneo.
    Devuelve {nombre_equipo: url_plantilla} y lo persiste en bronze.
    """
    cache_path = BRONZE_DIR / "tournament_page.html"
    html = _get_or_cache(driver, TOURNAMENT_URL, cache_path)
    soup = BeautifulSoup(html, "lxml")

    team_urls: dict[str, str] = {}
    for a in soup.select("a[href*='/en/squads/']"):
        href = a["href"]
        name = a.get_text(strip=True)
        if not name:
            continue
        if re.match(r"^/en/squads/[a-f0-9]+/.+-Men-Stats$", href):
            if name not in team_urls:
                team_urls[name] = BASE_URL + href

    print(f"\nEquipos encontrados: {len(team_urls)}")
    for name, url in sorted(team_urls.items()):
        print(f"  {name}: {url}")

    out = BRONZE_DIR / "team_urls.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(team_urls, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Guardado: {out}")

    return team_urls


# ---------------------------------------------------------------------------
# Step B2 — Descargar HTML de plantilla por equipo
# ---------------------------------------------------------------------------

def fetch_squad_html(driver: uc.Chrome, team_name: str, team_url: str) -> str:
    """Descarga y cachea el HTML de la página de stats de un equipo."""
    safe_name = re.sub(r"[^\w]", "_", team_name)
    cache_path = BRONZE_DIR / "squads" / f"{safe_name}.html"
    return _get_or_cache(driver, team_url, cache_path)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run() -> dict[str, str]:
    """
    Ejecuta la capa bronze completa.
    Se abre una ventana de Chrome — necesario para pasar Cloudflare Turnstile.
    """
    print("[INFO] Iniciando Chrome (undetected). Se abrirá una ventana...")
    driver = _create_driver()

    try:
        print("=== BRONZE: Descubriendo URLs de equipos ===")
        team_urls = discover_team_urls(driver)

        if not team_urls:
            print("[ERROR] No se encontraron equipos. Revisar URL del torneo.")
            return {}

        print("\n=== BRONZE: Descargando plantillas ===")
        for name, url in team_urls.items():
            fetch_squad_html(driver, name, url)

    finally:
        driver.quit()

    return team_urls


if __name__ == "__main__":
    run()
