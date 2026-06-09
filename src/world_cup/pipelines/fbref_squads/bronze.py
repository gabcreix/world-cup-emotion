"""
Bronze layer — FBref squads.

Descarga HTML crudo de FBref, lo guarda en disco (cache) y persiste
los registros crudos en bronze.fbref_squad_raw.

Usa undetected-chromedriver para pasar Cloudflare Turnstile.

Requiere:
    pip install undetected-chromedriver beautifulsoup4 lxml
    Chrome instalado en el sistema
"""

import json
import re
import time
from pathlib import Path

import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.webdriver.support.ui import WebDriverWait

from world_cup import db

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
REQUEST_DELAY = 6.0
CF_WAIT = 12.0


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _create_driver() -> uc.Chrome:
    options = uc.ChromeOptions()
    options.add_argument("--lang=en-US")
    options.add_argument("--window-size=1280,900")
    return uc.Chrome(options=options, headless=False, version_main=148)


def _fetch_html(driver: uc.Chrome, url: str) -> str:
    """Navega a url, espera Cloudflare y devuelve el HTML."""
    driver.get(url)
    try:
        WebDriverWait(driver, CF_WAIT).until(
            lambda d: d.title != "Just a moment..."
        )
    except Exception:
        print(f"  [WARN] Posible timeout de Cloudflare para {url}")
    time.sleep(3)
    return driver.page_source


def _get_or_cache(driver: uc.Chrome, url: str, cache_path: Path) -> str:
    """Devuelve HTML desde cache si es válido; si no, lo descarga y guarda."""
    if cache_path.exists():
        content = cache_path.read_text(encoding="utf-8", errors="ignore")
        if "Just a moment" in content or "challenge-platform" in content:
            print(f"  [cache-stale] Borrando: {cache_path.name}")
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
# Parseo mínimo para bronze (sin normalizar)
# ---------------------------------------------------------------------------

def _extract_raw_players(html: str) -> list[dict]:
    """
    Extrae filas de la tabla de plantilla como dicts crudos.
    Sin normalización: valores tal cual aparecen en FBref.
    """
    from bs4 import Comment

    soup = BeautifulSoup(html, "lxml")

    table = None
    for t in soup.find_all("table"):
        if "stats_standard" in t.get("id", "") or "roster" in t.get("id", ""):
            table = t
            break
    if table is None:
        for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
            if "stats_standard" not in comment and "roster" not in comment:
                continue
            inner = BeautifulSoup(comment, "lxml")
            for t in inner.find_all("table"):
                if "stats_standard" in t.get("id", "") or "roster" in t.get("id", ""):
                    table = t
                    break
            if table:
                break

    if table is None:
        return []

    players = []
    for row in table.select("tbody tr:not(.thead)"):
        name_cell = row.find("td", {"data-stat": "player"})
        if not name_cell or not name_cell.get_text(strip=True):
            continue

        link = name_cell.find("a")
        players.append({
            "player":       name_cell.get_text(strip=True),
            "position":     (row.find("td", {"data-stat": "position"}) or {}).get_text("", strip=True) if hasattr(row.find("td", {"data-stat": "position"}), "get_text") else "",
            "dob":          (row.find("td", {"data-stat": "dob"}) or {}).get_text("", strip=True) if hasattr(row.find("td", {"data-stat": "dob"}), "get_text") else "",
            "nationality":  (row.find("td", {"data-stat": "nationality"}) or {}).get_text("", strip=True) if hasattr(row.find("td", {"data-stat": "nationality"}), "get_text") else "",
            "fbref_url":    (BASE_URL + link["href"]) if link else None,
        })
    return players


# ---------------------------------------------------------------------------
# Persistencia en BD
# ---------------------------------------------------------------------------

def _persist_run(team_urls: dict[str, str], squads_dir: Path) -> str:
    """
    Inserta un run en bronze.fbref_squads_run y los jugadores crudos
    en bronze.fbref_squad_raw. Devuelve el run_id.
    """
    # Recopilar todos los registros antes de abrir la transacción
    records: list[tuple[str, str, dict]] = []
    for team_name, team_url in team_urls.items():
        safe_name = re.sub(r"[^\w]", "_", team_name)
        html_path = squads_dir / f"{safe_name}.html"
        if not html_path.exists():
            continue
        html = html_path.read_text(encoding="utf-8")
        raw_players = _extract_raw_players(html)
        for p in raw_players:
            records.append((team_name, team_url, p))

    num_equipos  = len(team_urls)
    num_jugadores = len(records)

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bronze.fbref_squads_run (num_equipos, num_jugadores)
                VALUES (%s, %s)
                RETURNING run_id
                """,
                (num_equipos, num_jugadores),
            )
            run_id = str(cur.fetchone()[0])

            for team_name, team_url, raw_json in records:
                cur.execute(
                    """
                    INSERT INTO bronze.fbref_squad_raw
                        (run_id, team_name_fbref, fbref_squad_url, raw_json)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (run_id, team_name, team_url, json.dumps(raw_json)),
                )
        conn.commit()

    print(f"\n  [BD] bronze — run_id: {run_id}")
    print(f"  [BD] {num_jugadores} registros en bronze.fbref_squad_raw")
    return run_id


# ---------------------------------------------------------------------------
# Discovery + download
# ---------------------------------------------------------------------------

def discover_team_urls(driver: uc.Chrome) -> dict[str, str]:
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
    return team_urls


def fetch_squad_html(driver: uc.Chrome, team_name: str, team_url: str) -> str:
    safe_name = re.sub(r"[^\w]", "_", team_name)
    cache_path = BRONZE_DIR / "squads" / f"{safe_name}.html"
    return _get_or_cache(driver, team_url, cache_path)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run(skip_db: bool = False) -> tuple[dict[str, str], str | None]:
    """
    Ejecuta la capa bronze completa.
    Devuelve (team_urls, run_id). run_id es None si skip_db=True.
    """
    print("[INFO] Iniciando Chrome (undetected). Se abrirá una ventana...")
    driver = _create_driver()

    try:
        print("=== BRONZE: Descubriendo URLs de equipos ===")
        team_urls = discover_team_urls(driver)

        if not team_urls:
            print("[ERROR] No se encontraron equipos.")
            return {}, None

        print("\n=== BRONZE: Descargando plantillas ===")
        for name, url in team_urls.items():
            fetch_squad_html(driver, name, url)

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    run_id = None
    if not skip_db:
        print("\n=== BRONZE: Persistiendo en BD ===")
        run_id = _persist_run(team_urls, BRONZE_DIR / "squads")

    return team_urls, run_id


if __name__ == "__main__":
    run()
