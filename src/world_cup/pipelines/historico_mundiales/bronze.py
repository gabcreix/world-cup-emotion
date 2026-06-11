"""
Bronze layer — Histórico de mundiales (1930-2022).

Descarga `tournaments.csv`, `matches.csv`, `goals.csv`, `player_appearances.csv`
y `players.csv` del dataset Fjelstul World Cup Database
(github.com/jfjelstul/worldcup), filtra a los 22 mundiales masculinos y
persiste las filas crudas en:
    - bronze.historico_edicion_raw   (una fila por edición)
    - bronze.historico_resultado_raw (una fila por partido)
    - bronze.historico_goleador_raw  (una fila por gol)
    - bronze.historico_aparicion_raw (una fila por aparición de jugador)
    - bronze.historico_jugador_raw   (una fila por jugador, con fecha de nacimiento)

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
GOALS_URL = (
    "https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv/goals.csv"
)
PLAYER_APPEARANCES_URL = (
    "https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv/player_appearances.csv"
)
PLAYERS_URL = (
    "https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv/players.csv"
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


def fetch_raw() -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    """Devuelve (ediciones, partidos, goles, apariciones, jugadores) filtrados
    a mundiales masculinos. `jugadores` se limita a los que aparecen en
    `apariciones`."""
    tournaments = _download_csv(TOURNAMENTS_URL)
    matches = _download_csv(MATCHES_URL)
    goals = _download_csv(GOALS_URL)
    appearances = _download_csv(PLAYER_APPEARANCES_URL)
    players = _download_csv(PLAYERS_URL)

    mens_ids = {t["tournament_id"] for t in tournaments if "Men's" in t["tournament_name"]}
    ediciones = [t for t in tournaments if t["tournament_id"] in mens_ids]
    resultados = [m for m in matches if m["tournament_id"] in mens_ids]
    goles = [g for g in goals if g["tournament_id"] in mens_ids]
    apariciones = [a for a in appearances if a["tournament_id"] in mens_ids]

    player_ids = {a["player_id"] for a in apariciones}
    jugadores = [p for p in players if p["player_id"] in player_ids]

    return ediciones, resultados, goles, apariciones, jugadores


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def _copy_raw(cur, table: str, run_id: str, rows: list[dict]) -> None:
    with cur.copy(f"COPY {table} (run_id, raw_json) FROM STDIN") as copy:
        for row in rows:
            copy.write_row((run_id, json.dumps(row)))


def _persist_run(
    ediciones: list[dict],
    resultados: list[dict],
    goles: list[dict],
    apariciones: list[dict],
    jugadores: list[dict],
) -> str:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bronze.historico_mundiales_run
                    (num_ediciones, num_partidos, num_goles, num_apariciones, num_jugadores)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING run_id
                """,
                (len(ediciones), len(resultados), len(goles), len(apariciones), len(jugadores)),
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

            _copy_raw(cur, "bronze.historico_goleador_raw", run_id, goles)
            _copy_raw(cur, "bronze.historico_aparicion_raw", run_id, apariciones)
            _copy_raw(cur, "bronze.historico_jugador_raw", run_id, jugadores)
        conn.commit()

    return run_id


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run() -> str:
    print("=== BRONZE: Descargando histórico de mundiales ===")
    ediciones, resultados, goles, apariciones, jugadores = fetch_raw()
    print(
        f"  {len(ediciones)} ediciones, {len(resultados)} partidos, "
        f"{len(goles)} goles, {len(apariciones)} apariciones, {len(jugadores)} jugadores"
    )

    print("\n=== BRONZE: Persistiendo en BD ===")
    run_id = _persist_run(ediciones, resultados, goles, apariciones, jugadores)
    print(f"  [BD] bronze — run_id: {run_id}")
    return run_id


if __name__ == "__main__":
    run()
