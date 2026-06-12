"""
Gold layer — FBref match reports.

Lee bronze.fbref_match_report_raw (partidos sin stats aún), parsea con
silver.parse_match_report y hace upsert idempotente en:
    - evento_partido (refresco completo por partido)
    - stats_equipo   (UNIQUE partido_id + participacion_id)
    - stats_jugador  (UNIQUE partido_id + jugador_id)

Resuelve:
    - jugador_id        vía alias_entidad (entidad_tipo='jugador'); si no hay
                         alias exacto, fuzzy match contra la convocatoria del
                         equipo y se registra el nombre de FBref como nuevo
                         alias para futuras ejecuciones
    - participacion_id  vía partido + seleccion.codigo_fifa
"""

import json
import re
import unicodedata

from rapidfuzz import fuzz

from world_cup import db
from world_cup.fbref_teams import FBREF_NAME_TO_FIFA
from world_cup.pipelines.fbref_match_stats import silver

SQUAD_HASH_RE = re.compile(r"/squads/([0-9a-f]{8})/")
FUZZY_THRESHOLD = 85

STATS_JUGADOR_FIELDS = (
    "minutos_jugados", "titular",
    "goles", "asistencias", "tiros", "tiros_a_puerta",
    "pases_completados", "pases_intentados", "pases_clave",
    "regates_exitosos", "regates_intentados", "conducciones",
    "presiones", "presiones_exitosas", "recuperaciones", "perdidas_balon",
    "duelos_ganados", "duelos_totales", "duelos_aereos_ganados",
    "intercepciones", "despejes", "entradas_exitosas",
    "tarjetas_amarillas", "tarjetas_rojas", "nota", "stats_extra_json",
)

STATS_EQUIPO_FIELDS = (
    "posesion", "tiros_totales", "tiros_a_puerta", "tiros_bloqueados",
    "pases_totales", "pases_completados", "pases_clave",
    "corners", "fueras_de_juego", "faltas_cometidas", "despejes",
)


# ---------------------------------------------------------------------------
# Lookups
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


def _load_jugador_por_alias(cur) -> dict[str, int]:
    cur.execute("SELECT alias, entidad_id FROM alias_entidad WHERE entidad_tipo = 'jugador'")
    mapping: dict[str, int] = {}
    for alias, jugador_id in cur.fetchall():
        mapping.setdefault(alias, jugador_id)
        mapping.setdefault(alias.lower(), jugador_id)
    return mapping


def _load_jugadores_por_participacion(cur) -> dict[int, list[tuple[int, str]]]:
    cur.execute(
        """
        SELECT c.participacion_id, j.jugador_id, j.nombre_completo
        FROM convocatoria c
        JOIN jugador j ON j.jugador_id = c.jugador_id
        """
    )
    mapping: dict[int, list[tuple[int, str]]] = {}
    for participacion_id, jugador_id, nombre_completo in cur.fetchall():
        mapping.setdefault(participacion_id, []).append((jugador_id, nombre_completo))
    return mapping


def _load_partido_info(cur, partido_id: int) -> dict | None:
    cur.execute(
        """
        SELECT p.participacion_local_id, p.participacion_visit_id,
               sl.codigo_fifa, sv.codigo_fifa
        FROM partido p
        JOIN participacion pl ON pl.participacion_id = p.participacion_local_id
        JOIN seleccion sl ON sl.seleccion_id = pl.seleccion_id
        JOIN participacion pv ON pv.participacion_id = p.participacion_visit_id
        JOIN seleccion sv ON sv.seleccion_id = pv.seleccion_id
        WHERE p.partido_id = %s
        """,
        (partido_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "participacion_local_id": row[0],
        "participacion_visit_id": row[1],
        "local_fifa": row[2],
        "visit_fifa": row[3],
    }


def _load_pendientes(cur) -> list[tuple[int, int, str]]:
    """(bronze_id, partido_id, html_raw) para partidos sin stats_equipo aún."""
    cur.execute(
        """
        SELECT r.id, r.partido_id, r.html_raw
        FROM bronze.fbref_match_report_raw r
        WHERE NOT EXISTS (
            SELECT 1 FROM stats_equipo se WHERE se.partido_id = r.partido_id
        )
        ORDER BY r.id
        """
    )
    return cur.fetchall()


# ---------------------------------------------------------------------------
# Resolución de jugador_id (alias exacto + fuzzy fallback)
# ---------------------------------------------------------------------------

def _normalize_name(nombre: str) -> str:
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", nombre) if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]+", " ", sin_acentos.lower()).strip()


def _resolve_jugador_id(cur, jugador_por_alias: dict[str, int],
                         jugadores_por_participacion: dict[int, list[tuple[int, str]]],
                         nombre: str | None, participacion_id: int) -> int | None:
    if not nombre:
        return None

    jugador_id = jugador_por_alias.get(nombre) or jugador_por_alias.get(nombre.lower())
    if jugador_id is not None:
        return jugador_id

    candidatos = jugadores_por_participacion.get(participacion_id, [])
    if not candidatos:
        return None

    norm_nombre = _normalize_name(nombre)
    mejor_id, mejor_score = None, 0.0
    for jid, nombre_completo in candidatos:
        score = fuzz.token_sort_ratio(norm_nombre, _normalize_name(nombre_completo))
        if score > mejor_score:
            mejor_id, mejor_score = jid, score

    if mejor_score < FUZZY_THRESHOLD:
        return None

    cur.execute(
        """
        INSERT INTO alias_entidad (entidad_tipo, entidad_id, alias, fuente, idioma, es_canonico)
        VALUES ('jugador', %s, %s, 'fbref', NULL, FALSE)
        ON CONFLICT (entidad_tipo, entidad_id, alias) DO NOTHING
        """,
        (mejor_id, nombre),
    )
    jugador_por_alias[nombre] = mejor_id
    jugador_por_alias[nombre.lower()] = mejor_id
    return mejor_id


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def _persist_eventos(cur, partido_id: int, eventos: list[dict],
                      jugador_por_alias: dict[str, int],
                      jugadores_por_participacion: dict[int, list[tuple[int, str]]],
                      participacion_por_lado: dict[str, int]) -> tuple[int, list[str]]:
    cur.execute("DELETE FROM evento_partido WHERE partido_id = %s", (partido_id,))

    creados = 0
    sin_match: list[str] = []

    for ev in eventos:
        participacion_id = participacion_por_lado[ev["equipo"]]

        jugador_id = _resolve_jugador_id(
            cur, jugador_por_alias, jugadores_por_participacion,
            ev["jugador"]["nombre"], participacion_id,
        )
        if jugador_id is None:
            sin_match.append(ev["jugador"]["nombre"])
            continue

        jugador_rel_id = None
        if ev["jugador_rel"]:
            jugador_rel_id = _resolve_jugador_id(
                cur, jugador_por_alias, jugadores_por_participacion,
                ev["jugador_rel"]["nombre"], participacion_id,
            )
            if jugador_rel_id is None:
                sin_match.append(ev["jugador_rel"]["nombre"])

        cur.execute(
            """
            INSERT INTO evento_partido
                (partido_id, jugador_id, jugador_rel_id, participacion_id,
                 tipo, minuto, minuto_adicional)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (partido_id, jugador_id, jugador_rel_id, participacion_id,
             ev["tipo"], ev["minuto"], ev["minuto_adicional"]),
        )
        creados += 1

    return creados, sin_match


def _persist_stats_equipo(cur, partido_id: int, participacion_id: int, stats: dict) -> None:
    columnas = ", ".join(STATS_EQUIPO_FIELDS)
    placeholders = ", ".join(f"%({c})s" for c in STATS_EQUIPO_FIELDS)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in STATS_EQUIPO_FIELDS)

    params = dict(stats)
    params["partido_id"] = partido_id
    params["participacion_id"] = participacion_id

    cur.execute(
        f"""
        INSERT INTO stats_equipo (partido_id, participacion_id, {columnas})
        VALUES (%(partido_id)s, %(participacion_id)s, {placeholders})
        ON CONFLICT (partido_id, participacion_id) DO UPDATE
        SET {updates}, actualizado_en = NOW()
        """,
        params,
    )


def _persist_stats_jugador(cur, partido_id: int, jugador_id: int, participacion_id: int,
                            stats: dict) -> None:
    columnas = ", ".join(STATS_JUGADOR_FIELDS)
    placeholders = ", ".join(f"%({c})s" for c in STATS_JUGADOR_FIELDS)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in STATS_JUGADOR_FIELDS)

    params = {c: stats.get(c) for c in STATS_JUGADOR_FIELDS}
    if params.get("stats_extra_json") is not None:
        params["stats_extra_json"] = json.dumps(params["stats_extra_json"])
    params["partido_id"] = partido_id
    params["jugador_id"] = jugador_id
    params["participacion_id"] = participacion_id

    cur.execute(
        f"""
        INSERT INTO stats_jugador (partido_id, jugador_id, participacion_id, {columnas})
        VALUES (%(partido_id)s, %(jugador_id)s, %(participacion_id)s, {placeholders})
        ON CONFLICT (partido_id, jugador_id) DO UPDATE
        SET {updates}, actualizado_en = NOW()
        """,
        params,
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run() -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            hash_to_fifa = _build_hash_to_fifa(cur)
            jugador_por_alias = _load_jugador_por_alias(cur)
            jugadores_por_participacion = _load_jugadores_por_participacion(cur)
            pendientes = _load_pendientes(cur)

    if not pendientes:
        print("[INFO] No hay match reports pendientes de procesar.")
        return

    print(f"  {len(pendientes)} match reports pendientes")

    eventos_creados = stats_equipo_creados = stats_jugador_creados = 0
    sin_match_jugadores: list[str] = []
    sin_match_partidos: list[int] = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for bronze_id, partido_id, html in pendientes:
                info = _load_partido_info(cur, partido_id)
                if info is None:
                    sin_match_partidos.append(partido_id)
                    continue

                datos = silver.parse_match_report(
                    html, hash_to_fifa, info["local_fifa"], info["visit_fifa"],
                )

                participacion_por_lado = {
                    "local": info["participacion_local_id"],
                    "visitante": info["participacion_visit_id"],
                }

                creados, sm = _persist_eventos(
                    cur, partido_id, datos["eventos"], jugador_por_alias,
                    jugadores_por_participacion, participacion_por_lado,
                )
                eventos_creados += creados
                sin_match_jugadores.extend(sm)

                for lado, participacion_id in participacion_por_lado.items():
                    equipo = datos["equipos"][lado]

                    _persist_stats_equipo(cur, partido_id, participacion_id, equipo["stats"])
                    stats_equipo_creados += 1

                    for jugador in equipo["jugadores"]:
                        jugador_id = _resolve_jugador_id(
                            cur, jugador_por_alias, jugadores_por_participacion,
                            jugador["nombre"], participacion_id,
                        )
                        if jugador_id is None:
                            sin_match_jugadores.append(jugador["nombre"])
                            continue
                        _persist_stats_jugador(cur, partido_id, jugador_id, participacion_id, jugador)
                        stats_jugador_creados += 1

                print(f"  [BD] partido {partido_id}: procesado (bronze_id={bronze_id})")

        conn.commit()

    print(f"\n  [BD] evento_partido: {eventos_creados} insertados")
    print(f"  [BD] stats_equipo: {stats_equipo_creados} upserts")
    print(f"  [BD] stats_jugador: {stats_jugador_creados} upserts")

    if sin_match_partidos:
        print(f"\n  [WARN] partidos sin info (FK rota?): {sin_match_partidos}")

    if sin_match_jugadores:
        unicos = sorted(set(sin_match_jugadores))
        print(f"\n  [WARN] jugadores sin match (ni alias ni fuzzy >= {FUZZY_THRESHOLD}) ({len(unicos)}):")
        for n in unicos[:20]:
            print(f"    - {n}")


if __name__ == "__main__":
    run()
