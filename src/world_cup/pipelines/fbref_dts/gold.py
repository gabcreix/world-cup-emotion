"""
Gold layer — FBref DTs (entrenadores).

Lee silver.fbref_dt (es_valido = true) y hace upsert en public.dt,
enlazando cada entrenador con la participación de su selección
en la edición 2026 (participacion.dt_id).

Nota: pais_id del DT se asigna por defecto al país de la selección que
dirige (no siempre coincide con su nacionalidad real, p. ej. seleccionadores
extranjeros). Se podrá refinar más adelante con la página individual del DT.
"""

from world_cup import db

EDICION_ANYO = 2026


def _load_lookups(cur) -> tuple[dict, dict]:
    """codigo_fifa -> pais_id, codigo_fifa -> participacion_id (2026)."""
    cur.execute("SELECT codigo_fifa, pais_id FROM pais")
    pais_por_fifa = dict(cur.fetchall())

    cur.execute(
        """
        SELECT s.codigo_fifa, pa.participacion_id
        FROM participacion pa
        JOIN seleccion s ON s.seleccion_id = pa.seleccion_id
        JOIN edicion e   ON e.edicion_id = pa.edicion_id
        WHERE e.anyo = %s
        """,
        (EDICION_ANYO,),
    )
    participacion_por_fifa = dict(cur.fetchall())

    return pais_por_fifa, participacion_por_fifa


def _load_silver_dts(cur, run_id: str) -> list[dict]:
    cur.execute(
        """
        SELECT nombre_completo, fecha_nacimiento, codigo_fifa, team_name_fbref
        FROM silver.fbref_dt
        WHERE run_id = %s AND es_valido = true
        """,
        (run_id,),
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _get_or_create_dt(cur, nombre_completo: str, fecha_nacimiento, pais_id: int) -> tuple[int, bool]:
    """Devuelve (dt_id, creado)."""
    cur.execute(
        "SELECT dt_id FROM dt WHERE nombre_completo = %s AND pais_id = %s",
        (nombre_completo, pais_id),
    )
    row = cur.fetchone()
    if row:
        dt_id = row[0]
        cur.execute(
            """
            UPDATE dt
            SET fecha_nacimiento = COALESCE(%s, fecha_nacimiento),
                actualizado_en = NOW()
            WHERE dt_id = %s
            """,
            (fecha_nacimiento, dt_id),
        )
        return dt_id, False

    cur.execute(
        """
        INSERT INTO dt (nombre_completo, fecha_nacimiento, pais_id)
        VALUES (%s, %s, %s)
        RETURNING dt_id
        """,
        (nombre_completo, fecha_nacimiento, pais_id),
    )
    return cur.fetchone()[0], True


def run(run_id: str) -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            pais_por_fifa, participacion_por_fifa = _load_lookups(cur)
            dts = _load_silver_dts(cur, run_id)

            creados = 0
            actualizados = 0
            sin_match: list[str] = []

            for d in dts:
                fifa = d["codigo_fifa"]
                pais_id = pais_por_fifa.get(fifa)
                participacion_id = participacion_por_fifa.get(fifa)

                if pais_id is None or participacion_id is None:
                    sin_match.append(f"{d['nombre_completo']} ({fifa})")
                    continue

                dt_id, creado = _get_or_create_dt(cur, d["nombre_completo"], d["fecha_nacimiento"], pais_id)
                cur.execute(
                    "UPDATE participacion SET dt_id = %s, actualizado_en = NOW() WHERE participacion_id = %s",
                    (dt_id, participacion_id),
                )

                if creado:
                    creados += 1
                else:
                    actualizados += 1

        conn.commit()

    print(f"  [BD] dt: {creados} creados, {actualizados} ya existentes (participacion enlazada)")
    if sin_match:
        print(f"\n  [WARN] Sin match ({len(sin_match)}):")
        for n in sin_match[:20]:
            print(f"    - {n}")


if __name__ == "__main__":
    raise SystemExit("Usar a través de world_cup.pipelines.fbref_dts.run")
