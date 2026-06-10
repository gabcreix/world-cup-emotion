"""
Silver layer — FBref DTs (entrenadores).

Lee bronze.fbref_dt_raw, elige el mejor candidato a entrenador
(Manager > Head Coach > Coach) por equipo y persiste en silver.fbref_dt.
También produce data/silver/fbref_dts/dts.json como copia local.
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
SILVER_DIR = ROOT / "data" / "silver" / "fbref_dts"

# ---------------------------------------------------------------------------
# Prioridad de etiquetas
# ---------------------------------------------------------------------------

LABEL_PRIORITY = ("manager", "head coach", "coach")

NAME_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")


# ---------------------------------------------------------------------------
# Selección del candidato + limpieza del nombre
# ---------------------------------------------------------------------------

def _pick_candidate(candidates: list[dict]) -> dict | None:
    if not candidates:
        return None

    def rank(c: dict) -> int:
        label = c["label"].lower()
        for i, prefix in enumerate(LABEL_PRIORITY):
            if label.startswith(prefix):
                return i
        return len(LABEL_PRIORITY)

    return sorted(candidates, key=rank)[0]


def _clean_name(value: str) -> str:
    return NAME_SUFFIX_RE.sub("", value).strip()


# ---------------------------------------------------------------------------
# Normalización de un registro bronze → silver
# ---------------------------------------------------------------------------

def _normalize(bronze_id: int, run_id: str, raw: dict, codigo_fifa: str, team_name: str) -> dict:
    es_valido = True
    motivo_invalido = None

    candidate = _pick_candidate(raw.get("manager_candidates", []))

    if candidate is None:
        es_valido = False
        motivo_invalido = "sin candidato a entrenador en #meta"
        nombre_completo = ""
        fbref_url = None
    else:
        nombre_completo = _clean_name(candidate["value"])
        fbref_url = candidate.get("fbref_url")
        if not nombre_completo:
            es_valido = False
            motivo_invalido = f"candidato vacío: {candidate!r}"

    return {
        "bronze_id":         bronze_id,
        "run_id":            run_id,
        "nombre_completo":   nombre_completo,
        "fbref_url":         fbref_url,
        "codigo_fifa":       codigo_fifa,
        "team_name_fbref":   team_name,
        "es_valido":         es_valido,
        "motivo_invalido":   motivo_invalido,
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
                    INSERT INTO silver.fbref_dt (
                        bronze_id, run_id,
                        nombre_completo, fbref_url,
                        codigo_fifa, team_name_fbref,
                        es_valido, motivo_invalido
                    ) VALUES (
                        %(bronze_id)s, %(run_id)s,
                        %(nombre_completo)s, %(fbref_url)s,
                        %(codigo_fifa)s, %(team_name_fbref)s,
                        %(es_valido)s, %(motivo_invalido)s
                    )
                    """,
                    r,
                )
        conn.commit()

    print(f"  [BD] {len(records)} registros en silver.fbref_dt")


# ---------------------------------------------------------------------------
# Lectura desde bronze en BD
# ---------------------------------------------------------------------------

def _load_from_bronze(run_id: str) -> list[tuple[int, str, str, dict]]:
    with db.get_cursor() as cur:
        cur.execute(
            """
            SELECT id, team_name_fbref, fbref_squad_url, raw_json
            FROM bronze.fbref_dt_raw
            WHERE run_id = %s
            ORDER BY team_name_fbref, id
            """,
            (run_id,),
        )
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run(run_id: str | None = None, skip_db: bool = False) -> list[dict]:
    if not run_id:
        print("[ERROR] Se requiere run_id (no hay fallback a disco para fbref_dts).")
        return []

    bronze_rows = _load_from_bronze(run_id)
    if not bronze_rows:
        print("[ERROR] No hay datos en bronze.")
        return []

    records: list[dict] = []
    skipped: list[str] = []
    invalidos: list[str] = []

    for bronze_id, team_name, _team_url, raw in bronze_rows:
        codigo_fifa = FBREF_NAME_TO_FIFA.get(team_name)
        if codigo_fifa is None:
            if team_name not in skipped:
                skipped.append(team_name)
            continue

        record = _normalize(bronze_id, run_id, raw, codigo_fifa, team_name)
        records.append(record)
        if not record["es_valido"]:
            invalidos.append(f"{team_name} ({codigo_fifa}): {record['motivo_invalido']}")

    for r in records:
        marca = "OK" if r["es_valido"] else "??"
        print(f"  [{marca}] {r['team_name_fbref']} ({r['codigo_fifa']}): {r['nombre_completo'] or '—'}")

    if skipped:
        print(f"\n  [Ignorados — no clasificados]: {', '.join(sorted(set(skipped)))}")
    if invalidos:
        print(f"\n  [WARN] {len(invalidos)} con incidencias:")
        for v in invalidos[:20]:
            print(f"    - {v}")

    if not skip_db:
        _persist_silver(records)

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    out = SILVER_DIR / "dts.json"
    out.write_text(json.dumps(records, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nGuardado local: {out}")

    return records


if __name__ == "__main__":
    raise SystemExit("Usar a través de world_cup.pipelines.fbref_dts.run")
