"""
Bronze layer — Histórico de mundiales (1930-2022).

Descarga `tournaments.csv` y `matches.csv` del dataset Fjelstul World Cup
Database (github.com/jfjelstul/worldcup), filtra a los 22 mundiales
masculinos y persiste las filas crudas en:
    - bronze.historico_edicion_raw   (una fila por edición)
    - bronze.historico_resultado_raw (una fila por partido)

Uso:
    python -m world_cup.pipelines.historico_mundiales.run
"""

import csv
import io
import json

import requests

from world_cup import db

TOURNAMENTS_URL = (
    "https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv/tournaments.csv"
)
MATCHES_URL = (
    "https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv/matches.csv"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Descarga
# ---------------------------------------------------------------------------

def _download_csv(url: str) -> list[dict]:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return list(csv.DictReader(io.StringIO(resp.text)))


def fetch_raw() -> tuple[list[dict], list[dict]]:
    """Devuelve (ediciones, partidos) filtrados a mundiales masculinos."""
    tournaments = _download_csv(TOURNAMENTS_URL)
    matches = _download_csv(MATCHES_URL)

    mens_ids = {t["tournament_id"] for t in tournaments if "Men's" in t["tournament_name"]}
    ediciones = [t for t in tournaments if t["tournament_id"] in mens_ids]
    resultados = [m for m in matches if m["tournament_id"] in mens_ids]

    return ediciones, resultados


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def _persist_run(ediciones: list[dict], resultados: list[dict]) -> str:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bronze.historico_mundiales_run (num_ediciones, num_partidos)
                VALUES (%s, %s)
                RETURNING run_id
                """,
                (len(ediciones), len(resultados)),
            )
            run_id = cur.fetchone()[0]

            for edicion in ediciones:
                cur.execute(
                    """
                    INSERT INTO bronze.historico_edicion_raw (run_id, raw_json)
                    VALUES (%s, %s)
                    """,
                    (run_id, json.dumps(edicion)),
                )

            for resultado in resultados:
                cur.execute(
                    """
                    INSERT INTO bronze.historico_resultado_raw (run_id, raw_json)
                    VALUES (%s, %s)
                    """,
                    (run_id, json.dumps(resultado)),
                )
        conn.commit()

    return run_id


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run() -> str:
    print("=== BRONZE: Descargando histórico de mundiales ===")
    ediciones, resultados = fetch_raw()
    print(f"  {len(ediciones)} ediciones, {len(resultados)} partidos")

    print("\n=== BRONZE: Persistiendo en BD ===")
    run_id = _persist_run(ediciones, resultados)
    print(f"  [BD] bronze — run_id: {run_id}")
    return run_id


if __name__ == "__main__":
    run()
