"""
Gold layer — Histórico de mundiales.

Lee la última run de bronze.historico_edicion_raw / historico_resultado_raw,
aplica las transformaciones de `transform.py` y hace upsert idempotente en
historico_edicion (UNIQUE anyo) e historico_resultado (UNIQUE match_id_externo).
"""

from world_cup import db
from world_cup.pipelines.historico_mundiales import transform


def _load_latest_run(cur) -> str:
    cur.execute(
        "SELECT run_id FROM bronze.historico_mundiales_run ORDER BY ejecutado_en DESC LIMIT 1"
    )
    return cur.fetchone()[0]


def _load_raw(cur, run_id: str) -> tuple[list[dict], list[dict]]:
    cur.execute(
        "SELECT raw_json FROM bronze.historico_edicion_raw WHERE run_id = %s", (run_id,)
    )
    ediciones = [row[0] for row in cur.fetchall()]

    cur.execute(
        "SELECT raw_json FROM bronze.historico_resultado_raw WHERE run_id = %s", (run_id,)
    )
    resultados = [row[0] for row in cur.fetchall()]

    return ediciones, resultados


def _load_pais_lookup(cur) -> dict[str, int]:
    cur.execute("SELECT codigo_fifa, pais_id FROM pais")
    return dict(cur.fetchall())


def _upsert_edicion(cur, edicion: dict, pais_por_fifa: dict[str, int]) -> tuple[int, bool, list[str]]:
    """Devuelve (historico_edicion_id, creado, avisos)."""
    avisos = []

    def _pais_id(codigo: str | None, campo: str) -> int | None:
        if codigo is None:
            return None
        pais_id = pais_por_fifa.get(codigo)
        if pais_id is None:
            avisos.append(f"{edicion['anyo']}: {campo} sin pais ({codigo})")
        return pais_id

    campeon_id = _pais_id(edicion["campeon_codigo_fifa"], "campeón")
    subcampeon_id = _pais_id(edicion["subcampeon_codigo_fifa"], "subcampeón")
    tercero_id = _pais_id(edicion["tercero_codigo_fifa"], "tercero")
    cuarto_id = _pais_id(edicion["cuarto_codigo_fifa"], "cuarto")

    cur.execute("SELECT historico_edicion_id FROM historico_edicion WHERE anyo = %s", (edicion["anyo"],))
    row = cur.fetchone()

    if row:
        cur.execute(
            """
            UPDATE historico_edicion
            SET sede = %s, num_equipos = %s,
                campeon_pais_id = %s, subcampeon_pais_id = %s,
                tercero_pais_id = %s, cuarto_pais_id = %s,
                goles_totales = %s, partidos_totales = %s,
                promedio_goles = %s, asistencia_total = %s,
                actualizado_en = NOW()
            WHERE historico_edicion_id = %s
            """,
            (edicion["sede"], edicion["num_equipos"],
             campeon_id, subcampeon_id, tercero_id, cuarto_id,
             edicion["goles_totales"], edicion["partidos_totales"],
             edicion["promedio_goles"], edicion["asistencia_total"],
             row[0]),
        )
        return row[0], False, avisos

    cur.execute(
        """
        INSERT INTO historico_edicion (
            anyo, sede, num_equipos,
            campeon_pais_id, subcampeon_pais_id, tercero_pais_id, cuarto_pais_id,
            goles_totales, partidos_totales, promedio_goles, asistencia_total
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING historico_edicion_id
        """,
        (edicion["anyo"], edicion["sede"], edicion["num_equipos"],
         campeon_id, subcampeon_id, tercero_id, cuarto_id,
         edicion["goles_totales"], edicion["partidos_totales"],
         edicion["promedio_goles"], edicion["asistencia_total"]),
    )
    return cur.fetchone()[0], True, avisos


def _upsert_resultado(cur, resultado: dict, historico_edicion_id: int,
                       pais_por_fifa: dict[str, int]) -> tuple[bool | None, list[str]]:
    """Devuelve (creado, avisos). creado es None si se omitió por falta de mapeo."""
    avisos = []
    local_id = pais_por_fifa.get(resultado["home_codigo_fifa"])
    visit_id = pais_por_fifa.get(resultado["away_codigo_fifa"])

    if local_id is None or visit_id is None:
        avisos.append(
            f"{resultado['match_id']}: equipo sin pais "
            f"({resultado['home_codigo_fifa']} / {resultado['away_codigo_fifa']})"
        )
        return None, avisos

    cur.execute(
        "SELECT historico_resultado_id FROM historico_resultado WHERE match_id_externo = %s",
        (resultado["match_id"],),
    )
    row = cur.fetchone()

    if row:
        cur.execute(
            """
            UPDATE historico_resultado
            SET historico_edicion_id = %s, fase = %s,
                pais_local_id = %s, pais_visitante_id = %s,
                goles_local = %s, goles_visitante = %s,
                goles_local_prorroga = %s, goles_visit_prorroga = %s,
                penaltis_local = %s, penaltis_visitante = %s,
                fecha = %s, actualizado_en = NOW()
            WHERE historico_resultado_id = %s
            """,
            (historico_edicion_id, resultado["fase"], local_id, visit_id,
             resultado["goles_local"], resultado["goles_visitante"],
             resultado["goles_local_prorroga"], resultado["goles_visit_prorroga"],
             resultado["penaltis_local"], resultado["penaltis_visitante"],
             resultado["fecha"], row[0]),
        )
        return False, avisos

    cur.execute(
        """
        INSERT INTO historico_resultado (
            historico_edicion_id, fase, pais_local_id, pais_visitante_id,
            goles_local, goles_visitante, goles_local_prorroga, goles_visit_prorroga,
            penaltis_local, penaltis_visitante, fecha, match_id_externo
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (historico_edicion_id, resultado["fase"], local_id, visit_id,
         resultado["goles_local"], resultado["goles_visitante"],
         resultado["goles_local_prorroga"], resultado["goles_visit_prorroga"],
         resultado["penaltis_local"], resultado["penaltis_visitante"],
         resultado["fecha"], resultado["match_id"]),
    )
    return True, avisos


def run() -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            run_id = _load_latest_run(cur)
            ediciones_raw, resultados_raw = _load_raw(cur, run_id)
            pais_por_fifa = _load_pais_lookup(cur)

            avisos: list[str] = []

            resultados = []
            for raw in resultados_raw:
                resultado = transform.build_resultado(raw)
                if resultado is None:
                    avisos.append(
                        f"{raw['match_id']}: fase o equipo sin mapeo "
                        f"({raw['stage_name']}, {raw['home_team_code']}/{raw['away_team_code']})"
                    )
                    continue
                resultados.append(resultado)

            ediciones_creadas = ediciones_actualizadas = 0
            resultados_creados = resultados_actualizados = resultados_omitidos = 0

            for raw in ediciones_raw:
                edicion = transform.build_edicion(raw, resultados)
                _, creado, avisos_edicion = _upsert_edicion(cur, edicion, pais_por_fifa)
                avisos.extend(avisos_edicion)
                if creado:
                    ediciones_creadas += 1
                else:
                    ediciones_actualizadas += 1

            cur.execute("SELECT anyo, historico_edicion_id FROM historico_edicion")
            edicion_id_por_anyo = dict(cur.fetchall())

            tournament_anyo = {raw["tournament_id"]: int(raw["year"]) for raw in ediciones_raw}

            for resultado in resultados:
                anyo = tournament_anyo.get(resultado["tournament_id"])
                historico_edicion_id = edicion_id_por_anyo.get(anyo)
                if historico_edicion_id is None:
                    avisos.append(f"{resultado['match_id']}: edición sin historico_edicion_id")
                    continue
                creado, avisos_resultado = _upsert_resultado(cur, resultado, historico_edicion_id, pais_por_fifa)
                avisos.extend(avisos_resultado)
                if creado is True:
                    resultados_creados += 1
                elif creado is False:
                    resultados_actualizados += 1
                else:
                    resultados_omitidos += 1

        conn.commit()

    print(f"  [BD] historico_edicion: {ediciones_creadas} creadas, {ediciones_actualizadas} actualizadas")
    print(
        f"  [BD] historico_resultado: {resultados_creados} creados, "
        f"{resultados_actualizados} actualizados, {resultados_omitidos} omitidos"
    )
    if avisos:
        print(f"\n  [WARN] Avisos ({len(avisos)}):")
        for a in avisos[:20]:
            print(f"    - {a}")


if __name__ == "__main__":
    run()
