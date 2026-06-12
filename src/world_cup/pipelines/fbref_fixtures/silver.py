"""
Silver layer — FBref fixtures.

Lee bronze.fbref_fixture_raw, normaliza y persiste en silver.fbref_fixture.
También produce data/silver/fbref_fixtures/fixtures.json como copia local.

Resuelve equipos a codigo_fifa via el hash de squad en las URLs de FBref,
cruzando con bronze.fbref_squad_raw + FBREF_NAME_TO_FIFA.
"""

import json
import re
from pathlib import Path

from world_cup import db
from world_cup.fbref_teams import FBREF_NAME_TO_FIFA

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[4]
SILVER_DIR = ROOT / "data" / "silver" / "fbref_fixtures"

# ---------------------------------------------------------------------------
# Mapeo ronda FBref → fase.codigo
# ---------------------------------------------------------------------------

ROUND_MAP: dict[str, str] = {
    "Group stage":          "GRP",
    "Round of 32":          "R32",
    "Round of 16":          "R16",
    "Quarter-finals":       "QF",
    "Semi-finals":          "SF",
    "3rd place match":      "TP",
    "Final":                "F",
}

SQUAD_HASH_RE = re.compile(r"/squads/([0-9a-f]+)/")
VENUE_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")
SCORE_RE = re.compile(r"^\s*(\d+)\s*[–\-:]\s*(\d+)")


# ---------------------------------------------------------------------------
# Lookup: hash de squad FBref → codigo_fifa
# ---------------------------------------------------------------------------

def _build_hash_to_fifa(cur) -> dict[str, str]:
    cur.execute("SELECT DISTINCT team_name_fbref, fbref_squad_url FROM bronze.fbref_squad_raw")
    mapping: dict[str, str] = {}
    for team_name, url in cur.fetchall():
        fifa = FBREF_NAME_TO_FIFA.get(team_name)
        if not fifa or not url:
            continue
        m = SQUAD_HASH_RE.search(url)
        if m:
            mapping[m.group(1)] = fifa
    return mapping


# ---------------------------------------------------------------------------
# Normalización de un registro bronze → silver
# ---------------------------------------------------------------------------

def _normalize(bronze_id: int, run_id: str, raw: dict, hash_to_fifa: dict[str, str]) -> dict:
    es_valido = True
    motivos: list[str] = []

    fecha = raw.get("date") or None

    hora_local = None
    start_time = raw.get("start_time", "")
    m = re.match(r"^(\d{1,2}:\d{2})", start_time)
    if m:
        hora_local = m.group(1)

    jornada = None
    if raw.get("gameweek", "").isdigit():
        jornada = int(raw["gameweek"])

    fase_raw = raw.get("round") or None
    fase_codigo = ROUND_MAP.get(fase_raw or "")
    if fase_raw and fase_codigo is None:
        motivos.append(f"ronda desconocida: {fase_raw!r}")

    equipo_local_fifa = None
    home_url = raw.get("home_team_url", "")
    m = SQUAD_HASH_RE.search(home_url)
    if m:
        equipo_local_fifa = hash_to_fifa.get(m.group(1))
    if equipo_local_fifa is None:
        motivos.append(f"equipo local sin match: {raw.get('home_team')!r}")

    equipo_visitante_fifa = None
    away_url = raw.get("away_team_url", "")
    m = SQUAD_HASH_RE.search(away_url)
    if m:
        equipo_visitante_fifa = hash_to_fifa.get(m.group(1))
    if equipo_visitante_fifa is None:
        motivos.append(f"equipo visitante sin match: {raw.get('away_team')!r}")

    venue_raw = VENUE_SUFFIX_RE.sub("", raw.get("venue", "")).strip() or None

    goles_local = goles_visitante = None
    score = raw.get("score", "")
    m = SCORE_RE.match(score)
    if m:
        goles_local, goles_visitante = int(m.group(1)), int(m.group(2))

    if not fecha:
        motivos.append("sin fecha")

    if motivos:
        es_valido = False

    return {
        "bronze_id":             bronze_id,
        "run_id":                run_id,
        "fecha":                 fecha,
        "hora_local":            hora_local,
        "jornada":               jornada,
        "fase_raw":              fase_raw,
        "fase_codigo":           fase_codigo,
        "equipo_local_fifa":     equipo_local_fifa,
        "equipo_visitante_fifa": equipo_visitante_fifa,
        "venue_raw":             venue_raw,
        "goles_local":           goles_local,
        "goles_visitante":       goles_visitante,
        "match_report_url":      raw.get("match_report_url") or None,
        "es_valido":             es_valido,
        "motivo_invalido":       "; ".join(motivos) or None,
    }


# ---------------------------------------------------------------------------
# Persistencia en BD
# ---------------------------------------------------------------------------

def _persist_silver(records: list[dict]) -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for r in records:
                cur.execute(
                    """
                    INSERT INTO silver.fbref_fixture (
                        bronze_id, run_id,
                        fecha, hora_local, jornada,
                        fase_raw, fase_codigo,
                        equipo_local_fifa, equipo_visitante_fifa,
                        venue_raw, goles_local, goles_visitante,
                        match_report_url,
                        es_valido, motivo_invalido
                    ) VALUES (
                        %(bronze_id)s, %(run_id)s,
                        %(fecha)s, %(hora_local)s, %(jornada)s,
                        %(fase_raw)s, %(fase_codigo)s,
                        %(equipo_local_fifa)s, %(equipo_visitante_fifa)s,
                        %(venue_raw)s, %(goles_local)s, %(goles_visitante)s,
                        %(match_report_url)s,
                        %(es_valido)s, %(motivo_invalido)s
                    )
                    """,
                    r,
                )
        conn.commit()

    print(f"  [BD] {len(records)} registros en silver.fbref_fixture")


# ---------------------------------------------------------------------------
# Lectura desde bronze en BD
# ---------------------------------------------------------------------------

def _load_from_bronze(cur, run_id: str) -> list[tuple[int, dict]]:
    cur.execute(
        """
        SELECT id, raw_json
        FROM bronze.fbref_fixture_raw
        WHERE run_id = %s
        ORDER BY id
        """,
        (run_id,),
    )
    return cur.fetchall()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run(run_id: str, skip_db: bool = False) -> list[dict]:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            hash_to_fifa = _build_hash_to_fifa(cur)
            bronze_rows = _load_from_bronze(cur, run_id)

    if not bronze_rows:
        print("[ERROR] No hay datos en bronze.")
        return []

    fixtures: list[dict] = []
    invalidos: list[str] = []

    for bronze_id, raw in bronze_rows:
        record = _normalize(bronze_id, run_id, raw, hash_to_fifa)
        fixtures.append(record)
        if not record["es_valido"]:
            invalidos.append(
                f"{raw.get('home_team')} vs {raw.get('away_team')} "
                f"({raw.get('date')}): {record['motivo_invalido']}"
            )

    print(f"  {len(fixtures)} partidos normalizados")
    if invalidos:
        print(f"\n  [WARN] {len(invalidos)} con incidencias:")
        for v in invalidos[:20]:
            print(f"    - {v}")

    if not skip_db:
        _persist_silver(fixtures)

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    out = SILVER_DIR / "fixtures.json"
    out.write_text(json.dumps(fixtures, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nGuardado local: {out}")

    return fixtures


if __name__ == "__main__":
    raise SystemExit("Usar a través de world_cup.pipelines.fbref_fixtures.run")
