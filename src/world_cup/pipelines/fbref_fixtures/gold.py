"""
Gold layer — FBref fixtures.

Lee silver.fbref_fixture (es_valido = true) y hace upsert en
public.partido para la edición 2026.

Resuelve:
    - fase_codigo       -> fase_id
    - equipo_*_fifa     -> participacion_id (vía seleccion + edición 2026)
    - grupo (fase GRP)  -> grupo_id (de la participación de los equipos)
    - venue_raw         -> estadio_id (vía alias_entidad)
"""

from world_cup import db

EDICION_ANYO = 2026


def _load_lookups(cur):
    cur.execute(
        """
        SELECT f.codigo, f.fase_id
        FROM fase f
        JOIN edicion e ON e.edicion_id = f.edicion_id
        WHERE e.anyo = %s
        """,
        (EDICION_ANYO,),
    )
    fase_por_codigo = dict(cur.fetchall())

    cur.execute(
        """
        SELECT s.codigo_fifa, pa.participacion_id, pa.grupo_id
        FROM participacion pa
        JOIN seleccion s ON s.seleccion_id = pa.seleccion_id
        JOIN edicion e   ON e.edicion_id = pa.edicion_id
        WHERE e.anyo = %s
        """,
        (EDICION_ANYO,),
    )
    participacion_por_fifa: dict[str, int] = {}
    grupo_por_fifa: dict[str, int | None] = {}
    for fifa, participacion_id, grupo_id in cur.fetchall():
        participacion_por_fifa[fifa] = participacion_id
        grupo_por_fifa[fifa] = grupo_id

    cur.execute("SELECT alias, entidad_id FROM alias_entidad WHERE entidad_tipo = 'estadio'")
    estadio_por_alias = dict(cur.fetchall())

    cur.execute("SELECT edicion_id FROM edicion WHERE anyo = %s", (EDICION_ANYO,))
    edicion_id = cur.fetchone()[0]

    return fase_por_codigo, participacion_por_fifa, grupo_por_fifa, estadio_por_alias, edicion_id


def _load_silver_fixtures(cur, run_id: str | None) -> list[dict]:
    if run_id:
        cur.execute(
            """
            SELECT fecha, hora_local, fase_codigo,
                   equipo_local_fifa, equipo_visitante_fifa,
                   venue_raw, goles_local, goles_visitante, match_report_url
            FROM silver.fbref_fixture
            WHERE run_id = %s AND es_valido = true
            """,
            (run_id,),
        )
    else:
        cur.execute(
            """
            SELECT DISTINCT ON (equipo_local_fifa, equipo_visitante_fifa)
                fecha, hora_local, fase_codigo,
                equipo_local_fifa, equipo_visitante_fifa,
                venue_raw, goles_local, goles_visitante, match_report_url
            FROM silver.fbref_fixture
            WHERE es_valido = true
            ORDER BY equipo_local_fifa, equipo_visitante_fifa, procesado_en DESC
            """
        )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _upsert_partido(cur, edicion_id: int, fase_id: int, grupo_id: int | None,
                     estadio_id: int | None, participacion_local_id: int,
                     participacion_visit_id: int, fecha_hora, estado: str,
                     goles_local: int | None, goles_visitante: int | None,
                     match_report_url: str | None) -> bool:
    """Devuelve True si se creó un partido nuevo, False si se actualizó uno existente."""
    cur.execute(
        """
        SELECT partido_id FROM partido
        WHERE edicion_id = %s
          AND participacion_local_id = %s
          AND participacion_visit_id = %s
        """,
        (edicion_id, participacion_local_id, participacion_visit_id),
    )
    row = cur.fetchone()

    if row:
        cur.execute(
            """
            UPDATE partido
            SET fase_id = %s, grupo_id = %s, estadio_id = %s,
                fecha_hora = %s, estado = %s,
                goles_local = %s, goles_visitante = %s,
                match_report_url = COALESCE(%s, match_report_url),
                actualizado_en = NOW()
            WHERE partido_id = %s
            """,
            (fase_id, grupo_id, estadio_id, fecha_hora, estado,
             goles_local, goles_visitante, match_report_url, row[0]),
        )
        return False

    cur.execute(
        """
        INSERT INTO partido (
            edicion_id, fase_id, grupo_id, estadio_id,
            participacion_local_id, participacion_visit_id,
            fecha_hora, estado, goles_local, goles_visitante, match_report_url
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (edicion_id, fase_id, grupo_id, estadio_id,
         participacion_local_id, participacion_visit_id,
         fecha_hora, estado, goles_local, goles_visitante, match_report_url),
    )
    return True


def run(run_id: str | None = None) -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            (fase_por_codigo, participacion_por_fifa, grupo_por_fifa,
             estadio_por_alias, edicion_id) = _load_lookups(cur)
            fixtures = _load_silver_fixtures(cur, run_id)

            creados = 0
            actualizados = 0
            sin_match: list[str] = []

            for f in fixtures:
                local_fifa = f["equipo_local_fifa"]
                visit_fifa = f["equipo_visitante_fifa"]

                fase_id = fase_por_codigo.get(f["fase_codigo"])
                participacion_local_id = participacion_por_fifa.get(local_fifa)
                participacion_visit_id = participacion_por_fifa.get(visit_fifa)

                if fase_id is None or participacion_local_id is None or participacion_visit_id is None:
                    sin_match.append(f"{local_fifa} vs {visit_fifa} ({f['fecha']}): fase/participación sin match")
                    continue

                grupo_id = None
                if f["fase_codigo"] == "GRP":
                    grupo_id = grupo_por_fifa.get(local_fifa)

                estadio_id = estadio_por_alias.get(f["venue_raw"]) if f["venue_raw"] else None

                fecha_hora = None
                if f["fecha"] and f["hora_local"]:
                    fecha_hora = f"{f['fecha']} {f['hora_local']}"
                elif f["fecha"]:
                    fecha_hora = f["fecha"]

                tiene_resultado = f["goles_local"] is not None and f["goles_visitante"] is not None
                estado = "finalizado" if tiene_resultado else "programado"

                creado = _upsert_partido(
                    cur, edicion_id, fase_id, grupo_id, estadio_id,
                    participacion_local_id, participacion_visit_id,
                    fecha_hora, estado, f["goles_local"], f["goles_visitante"],
                    f["match_report_url"],
                )

                if creado:
                    creados += 1
                else:
                    actualizados += 1

        conn.commit()

    print(f"  [BD] partido: {creados} creados, {actualizados} actualizados")
    if sin_match:
        print(f"\n  [WARN] Sin match ({len(sin_match)}):")
        for n in sin_match[:20]:
            print(f"    - {n}")


if __name__ == "__main__":
    run()
