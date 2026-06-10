"""
Silver layer — FBref squads.

Lee bronze.fbref_squad_raw, normaliza y persiste en silver.fbref_player.
También produce data/silver/fbref_squads/players.json como copia local.

Filtra equipos no clasificados al Mundial 2026 via FBREF_NAME_TO_FIFA.
"""

import json
from pathlib import Path

from world_cup import db
from world_cup.fbref_teams import FBREF_NAME_TO_FIFA

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[4]
SILVER_DIR = ROOT / "data" / "silver" / "fbref_squads"

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

VALID_POSICIONES = set(POSITION_MAP.keys())


# ---------------------------------------------------------------------------
# Normalización de un registro bronze → silver
# ---------------------------------------------------------------------------

def _normalize(bronze_id: int, run_id: str, raw: dict, codigo_fifa: str, team_name: str) -> dict:
    pos_raw = raw.get("position", "")
    posicion, posicion_especifica = POSITION_MAP.get(pos_raw, ("centrocampista", None))

    es_valido = True
    motivo_invalido = None
    if pos_raw and pos_raw not in VALID_POSICIONES:
        motivo_invalido = f"posicion desconocida: {pos_raw!r}"

    fecha_nacimiento = _parse_date(raw.get("dob", ""))

    return {
        "bronze_id":            bronze_id,
        "run_id":               run_id,
        "nombre_completo":      raw.get("player", "").strip(),
        "fecha_nacimiento":     fecha_nacimiento,
        "posicion":             posicion,
        "posicion_especifica":  posicion_especifica,
        "posicion_raw_fbref":   pos_raw or None,
        "nationality_raw":      raw.get("nationality", "") or None,
        "codigo_fifa":          codigo_fifa,
        "team_name_fbref":      team_name,
        "fbref_url":            raw.get("fbref_url"),
        "es_valido":            es_valido,
        "motivo_invalido":      motivo_invalido,
    }


def _parse_date(text: str) -> str | None:
    import datetime
    for fmt in ("%B %d, %Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Persistencia en BD
# ---------------------------------------------------------------------------

def _persist_silver(records: list[dict]) -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for r in records:
                cur.execute(
                    """
                    INSERT INTO silver.fbref_player (
                        bronze_id, run_id,
                        nombre_completo, fecha_nacimiento,
                        posicion, posicion_especifica, posicion_raw_fbref,
                        nationality_raw, codigo_fifa, team_name_fbref,
                        fbref_url, es_valido, motivo_invalido
                    ) VALUES (
                        %(bronze_id)s, %(run_id)s,
                        %(nombre_completo)s, %(fecha_nacimiento)s,
                        %(posicion)s, %(posicion_especifica)s, %(posicion_raw_fbref)s,
                        %(nationality_raw)s, %(codigo_fifa)s, %(team_name_fbref)s,
                        %(fbref_url)s, %(es_valido)s, %(motivo_invalido)s
                    )
                    """,
                    r,
                )
        conn.commit()

    print(f"  [BD] {len(records)} registros en silver.fbref_player")


# ---------------------------------------------------------------------------
# Lectura desde bronze en BD
# ---------------------------------------------------------------------------

def _load_from_bronze(run_id: str) -> list[tuple[int, str, str, dict]]:
    """
    Lee bronze.fbref_squad_raw para el run dado.
    Devuelve lista de (bronze_id, team_name_fbref, fbref_squad_url, raw_json).
    """
    with db.get_cursor() as cur:
        cur.execute(
            """
            SELECT id, team_name_fbref, fbref_squad_url, raw_json
            FROM bronze.fbref_squad_raw
            WHERE run_id = %s
            ORDER BY team_name_fbref, id
            """,
            (run_id,),
        )
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Fallback: leer desde archivos locales (cuando no hay run_id)
# ---------------------------------------------------------------------------

BRONZE_DIR = ROOT / "data" / "bronze" / "fbref_squads"


def _load_from_disk() -> list[tuple[int, str, str, dict]]:
    """
    Lee los HTMLs de bronze en disco y extrae los raw_json.
    Usado como fallback cuando no hay run_id de BD.
    bronze_id = 0 (no referenciado en BD).
    """
    from world_cup.pipelines.fbref_squads.bronze import _extract_raw_players

    squads_dir = BRONZE_DIR / "squads"
    team_urls_file = BRONZE_DIR / "team_urls.json"
    team_urls: dict[str, str] = {}
    if team_urls_file.exists():
        team_urls = json.loads(team_urls_file.read_text(encoding="utf-8"))

    rows = []
    for html_file in sorted(squads_dir.glob("*.html")):
        team_name = html_file.stem.replace("_", " ")
        url = team_urls.get(team_name, "")
        html = html_file.read_text(encoding="utf-8")
        for raw in _extract_raw_players(html):
            rows.append((0, team_name, url, raw))
    return rows


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run(run_id: str | None = None, skip_db: bool = False) -> list[dict]:
    """
    Normaliza registros bronze y los persiste en silver.fbref_player.

    Si run_id es None, lee desde los archivos locales en disco
    (útil para --silver-only sin haber persistido bronze en BD).
    """
    if run_id:
        print(f"  Leyendo bronze desde BD (run_id={run_id})...")
        bronze_rows = _load_from_bronze(run_id)
    else:
        print("  Leyendo bronze desde disco (sin run_id)...")
        bronze_rows = _load_from_disk()

    if not bronze_rows:
        print("[ERROR] No hay datos en bronze.")
        return []

    all_players: list[dict] = []
    skipped: list[str] = []
    teams_seen: set[str] = set()

    for bronze_id, team_name, team_url, raw in bronze_rows:
        codigo_fifa = FBREF_NAME_TO_FIFA.get(team_name)
        if codigo_fifa is None:
            if team_name not in skipped:
                skipped.append(team_name)
            continue

        record = _normalize(bronze_id, run_id or "local", raw, codigo_fifa, team_name)
        if record["nombre_completo"]:
            all_players.append(record)
            teams_seen.add(team_name)

    # Log por equipo
    from collections import Counter
    counts = Counter(r["team_name_fbref"] for r in all_players)
    for team, count in sorted(counts.items()):
        fifa = FBREF_NAME_TO_FIFA.get(team, "???")
        print(f"  {team} ({fifa}): {count} jugadores")

    if skipped:
        print(f"\n  [Ignorados — no clasificados]: {', '.join(sorted(set(skipped)))}")

    # Persistir en BD
    if not skip_db and run_id:
        _persist_silver(all_players)
    elif not skip_db and not run_id:
        print("  [INFO] Sin run_id — omitiendo persistencia en BD (usa --bronze-only + run completo)")

    # Guardar copia local
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    out = SILVER_DIR / "players.json"
    # Serializar: convertir fecha a string si viene como date object
    out.write_text(json.dumps(all_players, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"\nTotal jugadores (48 selecciones): {len(all_players)}")
    print(f"Guardado local: {out}")

    return all_players


if __name__ == "__main__":
    run()
