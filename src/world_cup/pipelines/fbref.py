"""
Pipeline FBref — jugadores y DTs del Mundial 2026.

Flujo:
  1. discover_team_urls()  → obtiene URLs de plantilla de cada selección
  2. scrape_squad()        → extrae jugadores de una selección
  3. (próximos pasos)       upsert en BD

Ejecutar desde la raíz del proyecto:
  python -m world_cup.pipelines.fbref
"""

import time
import json
import re
from pathlib import Path

import cloudscraper
from bs4 import BeautifulSoup

_scraper = cloudscraper.create_scraper()

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BASE_URL = "https://fbref.com"
TOURNAMENT_URL = f"{BASE_URL}/en/comps/1/2026/2026-FIFA-World-Cup-Stats"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://fbref.com/",
}

# Pausa entre requests para no saturar FBref (respetar robots.txt implícito)
REQUEST_DELAY = 4.0  # segundos

# Directorio donde se guardan los HTMLs cacheados
CACHE_DIR = Path(__file__).resolve().parents[4] / "data" / "fbref_cache"

# Mapeo posiciones FBref → enum de nuestra BD
POSITION_MAP = {
    "GK": ("portero", "portero"),
    "DF": ("defensa", None),
    "DF,MF": ("defensa", None),
    "MF,DF": ("centrocampista", None),
    "MF": ("centrocampista", None),
    "MF,FW": ("centrocampista", None),
    "FW,MF": ("delantero", None),
    "FW": ("delantero", None),
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get(url: str) -> BeautifulSoup:
    """GET con cache local en disco y delay cortés."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = re.sub(r"[^\w]", "_", url) + ".html"
    cache_path = CACHE_DIR / cache_key

    if cache_path.exists():
        print(f"  [cache] {url}")
        html = cache_path.read_text(encoding="utf-8")
    else:
        print(f"  [fetch] {url}")
        time.sleep(REQUEST_DELAY)
        r = _scraper.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        html = r.text
        cache_path.write_text(html, encoding="utf-8")

    return BeautifulSoup(html, "lxml")


# ---------------------------------------------------------------------------
# Step 1 — Descubrir URLs de plantillas
# ---------------------------------------------------------------------------

def discover_team_urls() -> dict[str, str]:
    """
    Extrae los links de plantilla de cada selección desde la página del torneo.
    Devuelve {nombre_equipo: url_plantilla}.
    """
    soup = _get(TOURNAMENT_URL)

    team_urls: dict[str, str] = {}

    # FBref lista equipos en una tabla con links a /en/squads/...
    for a in soup.select("a[href*='/en/squads/']"):
        href = a["href"]
        name = a.get_text(strip=True)
        if not name:
            continue
        # Nos quedamos solo con links de tipo /en/squads/<id>/<name>-Stats
        if re.match(r"^/en/squads/[a-f0-9]+/[\w-]+-Stats$", href):
            full_url = BASE_URL + href
            if name not in team_urls:
                team_urls[name] = full_url

    print(f"\nEquipos encontrados: {len(team_urls)}")
    for name, url in sorted(team_urls.items()):
        print(f"  {name}: {url}")

    return team_urls


# ---------------------------------------------------------------------------
# Step 2 — Extraer plantilla de un equipo
# ---------------------------------------------------------------------------

def scrape_squad(team_url: str, team_name: str) -> list[dict]:
    """
    Extrae la plantilla desde la página de stats de una selección.
    Devuelve lista de dicts con campos listos para insertar en `jugador`.
    """
    soup = _get(team_url)

    # La tabla estándar de plantilla en FBref tiene id="stats_standard_..."
    # o puede estar en un comentario HTML (FBref esconde tablas en comentarios)
    table = _find_squad_table(soup)
    if table is None:
        print(f"  [WARN] No se encontró tabla de plantilla para {team_name}")
        return []

    players = []
    for row in table.select("tbody tr:not(.thead)"):
        player = _parse_player_row(row, team_name)
        if player:
            players.append(player)

    print(f"  {team_name}: {len(players)} jugadores")
    return players


def _find_squad_table(soup: BeautifulSoup):
    """Busca la tabla de plantilla, incluso si está oculta en comentarios HTML."""
    import re as _re
    from bs4 import Comment

    # Primero intentar tabla visible
    for table in soup.find_all("table"):
        tid = table.get("id", "")
        if "stats_standard" in tid or "roster" in tid:
            return table

    # FBref a veces mete tablas dentro de comentarios HTML
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        if "stats_standard" in comment or "roster" in comment:
            inner = BeautifulSoup(comment, "lxml")
            for table in inner.find_all("table"):
                tid = table.get("id", "")
                if "stats_standard" in tid or "roster" in tid:
                    return table

    return None


def _parse_player_row(row, team_name: str) -> dict | None:
    """Parsea una fila de la tabla de plantilla."""
    cells = row.find_all(["td", "th"])
    if len(cells) < 4:
        return None

    # Nombre — siempre hay un <td data-stat="player">
    name_cell = row.find("td", {"data-stat": "player"})
    if not name_cell or not name_cell.get_text(strip=True):
        return None
    name = name_cell.get_text(strip=True)

    # Posición
    pos_cell = row.find("td", {"data-stat": "position"})
    pos_raw = pos_cell.get_text(strip=True) if pos_cell else ""
    posicion, posicion_especifica = POSITION_MAP.get(pos_raw, ("centrocampista", None))

    # Fecha de nacimiento
    dob_cell = row.find("td", {"data-stat": "birth_year"})
    # FBref puede tener data-stat="dob" o "birth_year"
    dob_full_cell = row.find("td", {"data-stat": "dob"})
    fecha_nacimiento = None
    if dob_full_cell:
        dob_text = dob_full_cell.get_text(strip=True)
        fecha_nacimiento = _parse_date(dob_text)

    # Nacionalidad (para cruzar con pais)
    nat_cell = row.find("td", {"data-stat": "nationality"})
    nationality = nat_cell.get_text(strip=True) if nat_cell else ""

    # Alias FBref (URL del jugador)
    player_link = name_cell.find("a")
    fbref_url = (BASE_URL + player_link["href"]) if player_link else None

    return {
        "nombre_completo": name,
        "posicion": posicion,
        "posicion_especifica": posicion_especifica,
        "fecha_nacimiento": fecha_nacimiento,
        "nationality_raw": nationality,
        "team_name": team_name,
        "fbref_url": fbref_url,
        "posicion_raw_fbref": pos_raw,
    }


def _parse_date(text: str) -> str | None:
    """Convierte texto de fecha FBref a formato ISO (YYYY-MM-DD)."""
    import datetime
    for fmt in ("%B %d, %Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# CLI rápido para probar
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Step 1: Descubriendo URLs de equipos ===")
    teams = discover_team_urls()

    # Guardar resultado para no repetir en cada ejecución
    out = Path(__file__).resolve().parents[4] / "data" / "fbref_team_urls.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(teams, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGuardado en {out}")

    if teams:
        # Probar con el primer equipo
        first_name, first_url = next(iter(teams.items()))
        print(f"\n=== Step 2: Scrapeando plantilla de '{first_name}' ===")
        players = scrape_squad(first_url, first_name)
        if players:
            print(f"\nPrimer jugador parseado:")
            print(json.dumps(players[0], indent=2, ensure_ascii=False))
