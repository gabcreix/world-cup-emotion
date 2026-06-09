"""
Silver layer — FBref squads.

Lee los HTMLs de bronze, parsea las tablas de plantilla y produce
registros limpios y normalizados en data/silver/fbref_squads/.

Filtra equipos que no participan en el Mundial 2026 cruzando
contra el mapeo canónico FBREF_NAME_TO_FIFA.

Salida: data/silver/fbref_squads/players.json
  Lista de dicts con campos:
    nombre_completo, posicion, posicion_especifica,
    fecha_nacimiento, codigo_fifa, fbref_url,
    posicion_raw_fbref, team_name_fbref
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
# Mapeo nombre FBref → codigo_fifa de nuestra BD
# Solo los 48 clasificados al Mundial 2026
# ---------------------------------------------------------------------------

FBREF_NAME_TO_FIFA: dict[str, str] = {
    "Algeria":              "ALG",
    "Argentina":            "ARG",
    "Australia":            "AUS",
    "Austria":              "AUT",
    "Belgium":              "BEL",
    "Bosnia Herzegovina":   "BIH",
    "Brazil":               "BRA",
    "Canada":               "CAN",
    "Cape Verde":           "CPV",
    "Colombia":             "COL",
    "Congo DR":             "COD",
    "Croatia":              "CRO",
    "Curaçao":              "CUW",
    "Czechia":              "CZE",
    "Côte d Ivoire":        "CIV",
    "Ecuador":              "ECU",
    "Egypt":                "EGY",
    "England":              "ENG",
    "France":               "FRA",
    "Germany":              "GER",
    "Ghana":                "GHA",
    "Haiti":                "HAI",
    "IR Iran":              "IRN",
    "Iraq":                 "IRQ",
    "Japan":                "JPN",
    "Jordan":               "JOR",
    "Korea Republic":       "KOR",
    "Mexico":               "MEX",
    "Morocco":              "MAR",
    "Netherlands":          "NED",
    "New Zealand":          "NZL",
    "Norway":               "NOR",
    "Panama":               "PAN",
    "Paraguay":             "PAR",
    "Portugal":             "POR",
    "Qatar":                "QAT",
    "Saudi Arabia":         "KSA",
    "Scotland":             "SCO",
    "Senegal":              "SEN",
    "South Africa":         "RSA",
    "Spain":                "ESP",
    "Sweden":               "SWE",
    "Switzerland":          "SUI",
    "Tunisia":              "TUN",
    "Türkiye":              "TUR",
    "United States":        "USA",
    "Uruguay":              "URU",
    "Uzbekistan":           "UZB",
}

# ---------------------------------------------------------------------------
# Mapeo posiciones FBref → enum BD
# ---------------------------------------------------------------------------

POSITION_MAP: dict[str, tuple[str, str | None]] = {
    "GK":    ("portero",         "portero"),
    "DF":    ("defensa",         "defensa_central"),
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
        if "stats_standard" in table.get("id", "") or "roster" in table.get("id", ""):
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


def _parse_player_row(row, codigo_fifa: str, team_name_fbref: str) -> dict | None:
    name_cell = row.find("td", {"data-stat": "player"})
    if not name_cell or not name_cell.get_text(strip=True):
        return None
    name = name_cell.get_text(strip=True)

    pos_cell = row.find("td", {"data-stat": "position"})
    pos_raw  = pos_cell.get_text(strip=True) if pos_cell else ""
    posicion, posicion_especifica = POSITION_MAP.get(pos_raw, ("centrocampista", None))

    dob_cell = row.find("td", {"data-stat": "dob"})
    fecha_nacimiento = _parse_date(dob_cell.get_text(strip=True)) if dob_cell else None

    nat_cell = row.find("td", {"data-stat": "nationality"})
    nationality = nat_cell.get_text(strip=True) if nat_cell else ""

    player_link = name_cell.find("a")
    fbref_url   = ("https://fbref.com" + player_link["href"]) if player_link else None

    return {
        "nombre_completo":      name,
        "posicion":             posicion,
        "posicion_especifica":  posicion_especifica,
        "fecha_nacimiento":     fecha_nacimiento,
        "nationality_raw":      nationality,
        "codigo_fifa":          codigo_fifa,
        "team_name_fbref":      team_name_fbref,
        "fbref_url":            fbref_url,
        "posicion_raw_fbref":   pos_raw,
    }


def parse_squad_html(html: str, team_name_fbref: str, codigo_fifa: str) -> list[dict]:
    soup  = BeautifulSoup(html, "lxml")
    table = _find_squad_table(soup)
    if table is None:
        return []

    players = []
    for row in table.select("tbody tr:not(.thead)"):
        p = _parse_player_row(row, codigo_fifa, team_name_fbref)
        if p:
            players.append(p)
    return players


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run() -> list[dict]:
    """
    Procesa HTMLs de bronze, filtra solo los 48 clasificados y produce
    players.json en silver.
    """
    squads_dir = BRONZE_DIR / "squads"
    if not squads_dir.exists():
        print("[ERROR] No hay HTMLs en bronze. Ejecuta bronze primero.")
        return []

    # Nombre de archivo → nombre FBref (inverso del safe_name)
    # Los archivos se llaman e.g. "Bosnia_Herzegovina.html" → "Bosnia Herzegovina"
    all_players: list[dict] = []
    skipped: list[str] = []

    for html_file in sorted(squads_dir.glob("*.html")):
        team_name = html_file.stem.replace("_", " ")
        codigo_fifa = FBREF_NAME_TO_FIFA.get(team_name)

        if codigo_fifa is None:
            skipped.append(team_name)
            continue

        html    = html_file.read_text(encoding="utf-8")
        players = parse_squad_html(html, team_name, codigo_fifa)
        print(f"  {team_name} ({codigo_fifa}): {len(players)} jugadores")
        all_players.extend(players)

    if skipped:
        print(f"\n  [Ignorados — no clasificados]: {', '.join(skipped)}")

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    out = SILVER_DIR / "players.json"
    out.write_text(json.dumps(all_players, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nTotal jugadores (48 selecciones): {len(all_players)}")
    print(f"Guardado: {out}")

    return all_players


if __name__ == "__main__":
    run()
