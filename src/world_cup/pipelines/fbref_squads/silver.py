"""
Silver layer — FBref squads.

Lee los HTMLs de bronze, parsea las tablas de plantilla y produce
registros limpios y normalizados en data/silver/fbref_squads/.

Salida: data/silver/fbref_squads/players.json
  Lista de dicts con campos:
    nombre_completo, posicion, posicion_especifica,
    fecha_nacimiento, codigo_fifa_seleccion,
    fbref_url, posicion_raw_fbref, team_name_fbref
"""

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup, Comment

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[4]
BRONZE_DIR = ROOT / "data" / "bronze" / "fbref_squads"
SILVER_DIR = ROOT / "data" / "silver" / "fbref_squads"

# ---------------------------------------------------------------------------
# Mapeo posiciones FBref → enum BD
# posicion general + posicion_especifica (None = no determinable sin más datos)
# ---------------------------------------------------------------------------

POSITION_MAP: dict[str, tuple[str, str | None]] = {
    "GK":    ("portero",         "portero"),
    "DF":    ("defensa",         "defensa_central"),   # refinado en gold si hay datos
    "DF,MF": ("defensa",         None),
    "MF,DF": ("centrocampista",  None),
    "MF":    ("centrocampista",  "mediocentro"),
    "MF,FW": ("centrocampista",  None),
    "FW,MF": ("delantero",       None),
    "FW":    ("delantero",       "delantero_centro"),
}


# ---------------------------------------------------------------------------
# Helpers de parseo
# ---------------------------------------------------------------------------

def _find_squad_table(soup: BeautifulSoup):
    """Busca la tabla de plantilla, incluso si está en comentarios HTML."""
    for table in soup.find_all("table"):
        tid = table.get("id", "")
        if "stats_standard" in tid or "roster" in tid:
            return table

    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        if "stats_standard" not in comment and "roster" not in comment:
            continue
        inner = BeautifulSoup(comment, "lxml")
        for table in inner.find_all("table"):
            if "stats_standard" in table.get("id", "") or "roster" in table.get("id", ""):
                return table

    return None


def _parse_date(text: str) -> str | None:
    import datetime
    for fmt in ("%B %d, %Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_player_row(row, team_name: str) -> dict | None:
    name_cell = row.find("td", {"data-stat": "player"})
    if not name_cell or not name_cell.get_text(strip=True):
        return None
    name = name_cell.get_text(strip=True)

    pos_cell  = row.find("td", {"data-stat": "position"})
    pos_raw   = pos_cell.get_text(strip=True) if pos_cell else ""
    posicion, posicion_especifica = POSITION_MAP.get(pos_raw, ("centrocampista", None))

    dob_cell  = row.find("td", {"data-stat": "dob"})
    fecha_nacimiento = _parse_date(dob_cell.get_text(strip=True)) if dob_cell else None

    nat_cell  = row.find("td", {"data-stat": "nationality"})
    nationality = nat_cell.get_text(strip=True) if nat_cell else ""

    player_link = name_cell.find("a")
    fbref_url   = ("https://fbref.com" + player_link["href"]) if player_link else None

    return {
        "nombre_completo":      name,
        "posicion":             posicion,
        "posicion_especifica":  posicion_especifica,
        "fecha_nacimiento":     fecha_nacimiento,
        "nationality_raw":      nationality,
        "team_name_fbref":      team_name,
        "fbref_url":            fbref_url,
        "posicion_raw_fbref":   pos_raw,
    }


def parse_squad_html(html: str, team_name: str) -> list[dict]:
    soup  = BeautifulSoup(html, "lxml")
    table = _find_squad_table(soup)
    if table is None:
        print(f"  [WARN] Sin tabla para {team_name}")
        return []

    players = []
    for row in table.select("tbody tr:not(.thead)"):
        p = _parse_player_row(row, team_name)
        if p:
            players.append(p)

    print(f"  {team_name}: {len(players)} jugadores")
    return players


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run() -> list[dict]:
    """
    Procesa todos los HTMLs de bronze y produce players.json en silver.
    Devuelve la lista de jugadores parseados.
    """
    squads_dir = BRONZE_DIR / "squads"
    if not squads_dir.exists():
        print("[ERROR] No hay HTMLs en bronze. Ejecuta bronze.py primero.")
        return []

    all_players: list[dict] = []

    for html_file in sorted(squads_dir.glob("*.html")):
        team_name = html_file.stem.replace("_", " ")
        html = html_file.read_text(encoding="utf-8")
        players = parse_squad_html(html, team_name)
        all_players.extend(players)

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    out = SILVER_DIR / "players.json"
    out.write_text(json.dumps(all_players, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nTotal jugadores: {len(all_players)}")
    print(f"Guardado: {out}")

    return all_players


if __name__ == "__main__":
    run()
