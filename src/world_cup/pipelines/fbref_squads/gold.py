"""
Gold layer — FBref squads.

Lee silver.fbref_player (es_valido = true) y hace upsert en
public.jugador y public.convocatoria para la edición 2026.

Vincula codigo_fifa -> pais / seleccion / participacion (edición 2026).
"""

from world_cup import db

EDICION_ANYO = 2026


def _load_lookup_tables(cur) -> tuple[dict, dict, dict]:
    """codigo_fifa -> pais_id, codigo_fifa -> seleccion_id, seleccion_id -> participacion_id (2026)."""
    cur.execute("SELECT codigo_fifa, pais_id FROM pais")
    pais_por_fifa = dict(cur.fetchall())

    cur.execute("SELECT codigo_fifa, seleccion_id FROM seleccion")
    seleccion_por_fifa = dict(cur.fetchall())

    cur.execute(
        """
        SELECT pa.seleccion_id, pa.participacion_id
        FROM participacion pa
        JOIN edicion e ON e.edicion_id = pa.edicion_id
        WHERE e.anyo = %s
        """,
        (EDICION_ANYO,),
    )
    participacion_por_seleccion = dict(cur.fetchall())

    return pais_por_fifa, seleccion_por_fifa, participacion_por_seleccion


def _load_silver_players(cur, run_id: str | None) -> list[dict]:
    if run_id:
        cur.execute(
            """
            SELECT nombre_completo, fecha_nacimiento, posicion, posicion_especifica, codigo_fifa
            FROM silver.fbref_player
            WHERE run_id = %s AND es_valido = true
            """,
            (run_id,),
        )
    else:
        cur.execute(
            """
            SELECT DISTINCT ON (nombre_completo, codigo_fifa)
                nombre_completo, fecha_nacimiento, posicion, posicion_especifica, codigo_fifa
            FROM silver.fbref_player
            WHERE es_valido = true
            ORDER BY nombre_completo, codigo_fifa, procesado_en DESC
            """
        )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _get_or_create_jugador(cur, p: dict, pais_id: int) -> tuple[int, bool]:
    """Devuelve (jugador_id, creado)."""
    cur.execute(
        "SELECT jugador_id FROM jugador WHERE nombre_completo = %s AND pais_id = %s",
        (p["nombre_completo"], pais_id),
    )
    row = cur.fetchone()
    if row:
        jugador_id = row[0]
        cur.execute(
            """
            UPDATE jugador
            SET fecha_nacimiento = COALESCE(%s, fecha_nacimiento),
                posicion = %s,
                posicion_especifica = COALESCE(%s, posicion_especifica),
                actualizado_en = NOW()
            WHERE jugador_id = %s
            """,
            (p["fecha_nacimiento"], p["posicion"], p["posicion_especifica"], jugador_id),
        )
        return jugador_id, False

    cur.execute(
        """
        INSERT INTO jugador (nombre_completo, fecha_nacimiento, pais_id, posicion, posicion_especifica)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING jugador_id
        """,
        (p["nombre_completo"], p["fecha_nacimiento"], pais_id, p["posicion"], p["posicion_especifica"]),
    )
    return cur.fetchone()[0], True


def _upsert_convocatoria(cur, jugador_id: int, participacion_id: int, posicion: str) -> None:
    cur.execute(
        """
        INSERT INTO convocatoria (jugador_id, participacion_id, posicion_convocado)
        VALUES (%s, %s, %s)
        ON CONFLICT (jugador_id, participacion_id) DO UPDATE
        SET posicion_convocado = EXCLUDED.posicion_convocado,
            actualizado_en = NOW()
        """,
        (jugador_id, participacion_id, posicion),
    )


def run(run_id: str | None = None) -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            pais_por_fifa, seleccion_por_fifa, participacion_por_seleccion = _load_lookup_tables(cur)
            players = _load_silver_players(cur, run_id)

            creados = 0
            actualizados = 0
            sin_match: list[str] = []

            for p in players:
                fifa = p["codigo_fifa"]
                pais_id = pais_por_fifa.get(fifa)
                seleccion_id = seleccion_por_fifa.get(fifa)
                participacion_id = participacion_por_seleccion.get(seleccion_id) if seleccion_id else None

                if pais_id is None or participacion_id is None:
                    sin_match.append(f"{p['nombre_completo']} ({fifa})")
                    continue

                jugador_id, creado = _get_or_create_jugador(cur, p, pais_id)
                _upsert_convocatoria(cur, jugador_id, participacion_id, p["posicion"])

                if creado:
                    creados += 1
                else:
                    actualizados += 1

        conn.commit()

    print(f"  [BD] jugador: {creados} creados, {actualizados} actualizados")
    print(f"  [BD] convocatoria: {creados + actualizados} upserts (edición {EDICION_ANYO})")
    if sin_match:
        print(f"\n  [WARN] Sin match pais/participacion ({len(sin_match)}):")
        for n in sin_match[:10]:
            print(f"    - {n}")


if __name__ == "__main__":
    run()
