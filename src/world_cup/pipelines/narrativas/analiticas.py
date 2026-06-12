"""
Narrativas — Analíticas del torneo actual.

Queries predefinidas sobre los datos del Mundial 2026 (`partido`,
`evento_partido`, `stats_equipo`, `participacion`, ...) que identifican
datos destacables para convertir en filas de `narrativa`.

Cada función devuelve `None` si no hay datos suficientes (se omite esa
narrativa) o un dict con:
    - titulo: frase breve y determinista (sirve de clave para idempotencia)
    - tipo: 'estadistica' | 'racha' | 'comparativa' | 'hito' | 'curiosidad'
    - score_relevancia: float 0-1
    - entidades_json: lista de {"tipo": ..., "id": ...}
    - contexto: dict con los datos estructurados, para que el LLM redacte
      la descripción
"""

EDICION_ANYO = 2026


def load_edicion_id(cur) -> int:
    cur.execute("SELECT edicion_id FROM edicion WHERE anyo = %s", (EDICION_ANYO,))
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Selecciones invictas
# ---------------------------------------------------------------------------

def invictos(cur, edicion_id: int) -> dict | None:
    cur.execute(
        """
        WITH resultados AS (
            SELECT
                pa.participacion_id,
                CASE WHEN pa.participacion_id = part.participacion_local_id
                     THEN part.goles_local ELSE part.goles_visitante END AS goles_favor,
                CASE WHEN pa.participacion_id = part.participacion_local_id
                     THEN part.goles_visitante ELSE part.goles_local END AS goles_contra
            FROM partido part
            JOIN participacion pa
                 ON pa.participacion_id IN (part.participacion_local_id, part.participacion_visit_id)
            WHERE part.edicion_id = %(edicion_id)s AND part.estado = 'finalizado'
        )
        SELECT pa.participacion_id, pa.seleccion_id, p.nombre, p.codigo_iso2,
               COUNT(*) AS pj,
               COUNT(*) FILTER (WHERE r.goles_favor > r.goles_contra) AS victorias,
               COUNT(*) FILTER (WHERE r.goles_favor = r.goles_contra) AS empates
        FROM resultados r
        JOIN participacion pa ON pa.participacion_id = r.participacion_id
        JOIN seleccion s ON s.seleccion_id = pa.seleccion_id
        JOIN pais p ON p.pais_id = s.pais_id
        GROUP BY pa.participacion_id, pa.seleccion_id, p.nombre, p.codigo_iso2
        HAVING COUNT(*) FILTER (WHERE r.goles_favor < r.goles_contra) = 0
        ORDER BY pj DESC, victorias DESC, p.nombre
        """,
        {"edicion_id": edicion_id},
    )
    cols = [c.name for c in cur.description]
    filas = [dict(zip(cols, row)) for row in cur.fetchall()]

    # Solo es noticia si al menos una selección lleva 2+ partidos sin perder.
    candidatas = [f for f in filas if f["pj"] >= 2]
    if not candidatas:
        return None

    max_pj = candidatas[0]["pj"]
    lideres = [f for f in candidatas if f["pj"] == max_pj]
    nombres = ", ".join(f["nombre"] for f in lideres)

    return {
        "titulo": f"Selecciones invictas tras {max_pj} partidos: {nombres}",
        "tipo": "racha",
        "fuente_datos": "torneo_actual",
        "score_relevancia": min(1.0, 0.3 + 0.15 * max_pj),
        "entidades_json": [{"tipo": "seleccion", "id": f["seleccion_id"]} for f in lideres],
        "contexto": {
            "tipo_narrativa": "racha_invicta",
            "edicion": EDICION_ANYO,
            "selecciones": [
                {
                    "nombre": f["nombre"], "partidos_jugados": f["pj"],
                    "victorias": f["victorias"], "empates": f["empates"],
                }
                for f in lideres
            ],
        },
    }


# ---------------------------------------------------------------------------
# Máximo goleador del torneo
# ---------------------------------------------------------------------------

def goleadores(cur, edicion_id: int) -> dict | None:
    cur.execute(
        """
        SELECT j.jugador_id, j.nombre_completo, p.nombre AS pais, COUNT(*) AS goles
        FROM evento_partido e
        JOIN jugador j ON j.jugador_id = e.jugador_id
        JOIN participacion pa ON pa.participacion_id = e.participacion_id
        JOIN seleccion s ON s.seleccion_id = pa.seleccion_id
        JOIN pais p ON p.pais_id = s.pais_id
        JOIN partido part ON part.partido_id = e.partido_id
        WHERE part.edicion_id = %(edicion_id)s AND e.tipo IN ('gol', 'gol_penalti')
        GROUP BY j.jugador_id, j.nombre_completo, p.nombre
        ORDER BY goles DESC, j.nombre_completo
        """,
        {"edicion_id": edicion_id},
    )
    cols = [c.name for c in cur.description]
    filas = [dict(zip(cols, row)) for row in cur.fetchall()]
    if not filas:
        return None

    max_goles = filas[0]["goles"]
    lideres = [f for f in filas if f["goles"] == max_goles]
    nombres = ", ".join(f"{f['nombre_completo']} ({f['pais']})" for f in lideres)

    return {
        "titulo": f"Máximo goleador del torneo ({max_goles} goles): {nombres}",
        "tipo": "estadistica",
        "fuente_datos": "torneo_actual",
        "score_relevancia": min(1.0, 0.3 + 0.15 * max_goles),
        "entidades_json": [{"tipo": "jugador", "id": f["jugador_id"]} for f in lideres],
        "contexto": {
            "tipo_narrativa": "maximo_goleador",
            "edicion": EDICION_ANYO,
            "goleadores": filas[:5],
        },
    }


# ---------------------------------------------------------------------------
# Partido con más goles
# ---------------------------------------------------------------------------

def partido_mas_goles(cur, edicion_id: int) -> dict | None:
    cur.execute(
        """
        SELECT part.partido_id, part.fecha_hora,
               pl.nombre AS local, pv.nombre AS visitante,
               part.goles_local, part.goles_visitante,
               (part.goles_local + part.goles_visitante) AS total_goles,
               f.codigo AS fase, g.letra AS grupo
        FROM partido part
        JOIN fase f ON f.fase_id = part.fase_id
        LEFT JOIN grupo g ON g.grupo_id = part.grupo_id
        JOIN participacion pal ON pal.participacion_id = part.participacion_local_id
        JOIN seleccion sl ON sl.seleccion_id = pal.seleccion_id
        JOIN pais pl ON pl.pais_id = sl.pais_id
        JOIN participacion pav ON pav.participacion_id = part.participacion_visit_id
        JOIN seleccion sv ON sv.seleccion_id = pav.seleccion_id
        JOIN pais pv ON pv.pais_id = sv.pais_id
        WHERE part.edicion_id = %(edicion_id)s AND part.estado = 'finalizado'
        ORDER BY total_goles DESC, part.fecha_hora ASC
        LIMIT 1
        """,
        {"edicion_id": edicion_id},
    )
    row = cur.fetchone()
    if not row or row[6] == 0:
        return None

    cols = [c.name for c in cur.description]
    p = dict(zip(cols, row))

    return {
        "titulo": (
            f"Partido más goleado del torneo: {p['local']} {p['goles_local']}-"
            f"{p['goles_visitante']} {p['visitante']} ({p['total_goles']} goles)"
        ),
        "tipo": "estadistica",
        "fuente_datos": "torneo_actual",
        "score_relevancia": min(1.0, 0.2 + 0.1 * p["total_goles"]),
        "entidades_json": [{"tipo": "partido", "id": p["partido_id"]}],
        "contexto": {
            "tipo_narrativa": "partido_mas_goleado",
            "edicion": EDICION_ANYO,
            "partido": {
                "local": p["local"], "visitante": p["visitante"],
                "goles_local": p["goles_local"], "goles_visitante": p["goles_visitante"],
                "fase": p["fase"], "grupo": p["grupo"],
                "fecha": p["fecha_hora"].date().isoformat() if p["fecha_hora"] else None,
            },
        },
    }


# ---------------------------------------------------------------------------
# Mejor posesión media
# ---------------------------------------------------------------------------

def mejor_posesion(cur, edicion_id: int) -> dict | None:
    cur.execute(
        """
        SELECT pa.seleccion_id, p.nombre, AVG(se.posesion) AS posesion_media, COUNT(*) AS partidos
        FROM stats_equipo se
        JOIN participacion pa ON pa.participacion_id = se.participacion_id
        JOIN seleccion s ON s.seleccion_id = pa.seleccion_id
        JOIN pais p ON p.pais_id = s.pais_id
        WHERE pa.edicion_id = %(edicion_id)s AND se.posesion IS NOT NULL
        GROUP BY pa.seleccion_id, p.nombre
        HAVING COUNT(*) >= 1
        ORDER BY posesion_media DESC
        LIMIT 1
        """,
        {"edicion_id": edicion_id},
    )
    row = cur.fetchone()
    if not row:
        return None

    cols = [c.name for c in cur.description]
    f = dict(zip(cols, row))

    return {
        "titulo": f"Mejor posesión media del torneo: {f['nombre']} ({float(f['posesion_media']):.1f}%)",
        "tipo": "estadistica",
        "fuente_datos": "torneo_actual",
        "score_relevancia": 0.5,
        "entidades_json": [{"tipo": "seleccion", "id": f["seleccion_id"]}],
        "contexto": {
            "tipo_narrativa": "mejor_posesion",
            "edicion": EDICION_ANYO,
            "seleccion": f["nombre"],
            "posesion_media": round(float(f["posesion_media"]), 1),
            "partidos": f["partidos"],
        },
    }


# ---------------------------------------------------------------------------
# Grupo más goleador
# ---------------------------------------------------------------------------

def grupo_mas_goleador(cur, edicion_id: int) -> dict | None:
    cur.execute(
        """
        SELECT g.grupo_id, g.letra,
               AVG(part.goles_local + part.goles_visitante) AS media_goles,
               COUNT(*) AS partidos
        FROM partido part
        JOIN fase f ON f.fase_id = part.fase_id AND f.codigo = 'GRP'
        JOIN grupo g ON g.grupo_id = part.grupo_id
        WHERE part.edicion_id = %(edicion_id)s AND part.estado = 'finalizado'
        GROUP BY g.grupo_id, g.letra
        ORDER BY media_goles DESC, partidos DESC
        LIMIT 1
        """,
        {"edicion_id": edicion_id},
    )
    row = cur.fetchone()
    if not row:
        return None

    cols = [c.name for c in cur.description]
    f = dict(zip(cols, row))

    return {
        "titulo": (
            f"Grupo más goleador hasta ahora: Grupo {f['letra']} "
            f"({float(f['media_goles']):.2f} goles/partido en {f['partidos']} partidos)"
        ),
        "tipo": "curiosidad",
        "fuente_datos": "torneo_actual",
        "score_relevancia": 0.4,
        "entidades_json": [{"tipo": "grupo", "id": f["grupo_id"]}],
        "contexto": {
            "tipo_narrativa": "grupo_mas_goleador",
            "edicion": EDICION_ANYO,
            "grupo": f["letra"],
            "media_goles": round(float(f["media_goles"]), 2),
            "partidos": f["partidos"],
        },
    }


# ---------------------------------------------------------------------------
# Vallas invictas
# ---------------------------------------------------------------------------

def vallas_invictas(cur, edicion_id: int) -> dict | None:
    cur.execute(
        """
        SELECT pa.seleccion_id, p.nombre, COUNT(DISTINCT part.partido_id) AS partidos
        FROM partido part
        JOIN participacion pa
             ON pa.participacion_id IN (part.participacion_local_id, part.participacion_visit_id)
        JOIN seleccion s ON s.seleccion_id = pa.seleccion_id
        JOIN pais p ON p.pais_id = s.pais_id
        WHERE part.edicion_id = %(edicion_id)s AND part.estado = 'finalizado'
          AND NOT EXISTS (
              SELECT 1 FROM evento_partido e
              WHERE e.partido_id = part.partido_id
                AND e.participacion_id != pa.participacion_id
                AND e.tipo IN ('gol', 'gol_penalti', 'gol_propia')
          )
        GROUP BY pa.seleccion_id, p.nombre
        HAVING COUNT(DISTINCT part.partido_id) >= 2
        ORDER BY partidos DESC, p.nombre
        """,
        {"edicion_id": edicion_id},
    )

    cols = [c.name for c in cur.description]
    filas = [dict(zip(cols, row)) for row in cur.fetchall()]
    if not filas:
        return None

    nombres = ", ".join(f["nombre"] for f in filas)
    max_p = filas[0]["partidos"]

    return {
        "titulo": f"Porterías a cero en {max_p} partidos: {nombres}",
        "tipo": "estadistica",
        "fuente_datos": "torneo_actual",
        "score_relevancia": min(1.0, 0.35 + 0.15 * max_p),
        "entidades_json": [{"tipo": "seleccion", "id": f["seleccion_id"]} for f in filas],
        "contexto": {
            "tipo_narrativa": "vallas_invictas",
            "edicion": EDICION_ANYO,
            "selecciones": [{"nombre": f["nombre"], "partidos": f["partidos"]} for f in filas],
        },
    }


# ---------------------------------------------------------------------------
# Racha goleadora individual
# ---------------------------------------------------------------------------

def racha_goleadora_jugador(cur, edicion_id: int) -> dict | None:
    cur.execute(
        """
        WITH goles_por_partido AS (
            SELECT e.jugador_id, part.partido_id, part.fecha_hora,
                   ROW_NUMBER() OVER (PARTITION BY e.jugador_id ORDER BY part.fecha_hora) AS rn
            FROM evento_partido e
            JOIN partido part ON part.partido_id = e.partido_id
            WHERE part.edicion_id = %(edicion_id)s
              AND part.estado = 'finalizado'
              AND e.tipo IN ('gol', 'gol_penalti')
            GROUP BY e.jugador_id, part.partido_id, part.fecha_hora
        )
        SELECT jugador_id, COUNT(*) AS partidos_con_gol
        FROM goles_por_partido
        GROUP BY jugador_id
        HAVING COUNT(*) >= 2
        ORDER BY partidos_con_gol DESC
        LIMIT 1
        """,
        {"edicion_id": edicion_id},
    )

    row = cur.fetchone()
    if not row:
        return None

    jugador_id, racha = row
    cur.execute(
        "SELECT nombre_completo FROM jugador WHERE jugador_id = %s", (jugador_id,)
    )
    nombre = cur.fetchone()[0]

    return {
        "titulo": f"Racha goleadora: {nombre} ha marcado en {racha} partidos consecutivos",
        "tipo": "racha",
        "fuente_datos": "torneo_actual",
        "score_relevancia": min(1.0, 0.4 + 0.15 * racha),
        "entidades_json": [{"tipo": "jugador", "id": jugador_id}],
        "contexto": {
            "tipo_narrativa": "racha_goleadora_jugador",
            "edicion": EDICION_ANYO,
            "jugador": nombre,
            "partidos_con_gol": racha,
        },
    }


# ---------------------------------------------------------------------------
# Peor defensa del torneo
# ---------------------------------------------------------------------------

def peor_defensa(cur, edicion_id: int) -> dict | None:
    cur.execute(
        """
        SELECT pa.seleccion_id, p.nombre,
               SUM(CASE WHEN pa.participacion_id = part.participacion_local_id
                        THEN part.goles_visitante ELSE part.goles_local END) AS goles_encajados,
               COUNT(*) AS partidos
        FROM partido part
        JOIN participacion pa
             ON pa.participacion_id IN (part.participacion_local_id, part.participacion_visit_id)
        JOIN seleccion s ON s.seleccion_id = pa.seleccion_id
        JOIN pais p ON p.pais_id = s.pais_id
        WHERE part.edicion_id = %(edicion_id)s AND part.estado = 'finalizado'
        GROUP BY pa.seleccion_id, p.nombre
        HAVING COUNT(*) >= 2
        ORDER BY goles_encajados DESC
        LIMIT 1
        """,
        {"edicion_id": edicion_id},
    )

    row = cur.fetchone()
    if not row or row[2] == 0:
        return None

    cols = ["seleccion_id", "nombre", "goles_encajados", "partidos"]
    f = dict(zip(cols, row))

    return {
        "titulo": (
            f"Defensa más perforada: {f['nombre']} ha encajado "
            f"{f['goles_encajados']} goles en {f['partidos']} partidos"
        ),
        "tipo": "estadistica",
        "fuente_datos": "torneo_actual",
        "score_relevancia": min(1.0, 0.2 + 0.1 * f["goles_encajados"]),
        "entidades_json": [{"tipo": "seleccion", "id": f["seleccion_id"]}],
        "contexto": {
            "tipo_narrativa": "peor_defensa",
            "edicion": EDICION_ANYO,
            "seleccion": f["nombre"],
            "goles_encajados": f["goles_encajados"],
            "partidos": f["partidos"],
        },
    }


# ---------------------------------------------------------------------------
# Score según fase del torneo
# ---------------------------------------------------------------------------

_FASE_MULTIPLIER: dict[str, float] = {
    "GRP": 1.0,
    "R32": 1.2,
    "R16": 1.4,
    "QF": 1.6,
    "SF": 1.8,
    "TP": 1.5,
    "F": 2.0,
}


def _fase_actual(cur, edicion_id: int) -> str:
    """Devuelve el código de la fase más avanzada con partidos finalizados."""
    cur.execute(
        """
        SELECT f.codigo
        FROM partido p
        JOIN fase f ON f.fase_id = p.fase_id
        WHERE p.edicion_id = %s AND p.estado = 'finalizado'
        ORDER BY f.orden DESC
        LIMIT 1
        """,
        (edicion_id,),
    )
    row = cur.fetchone()
    return row[0] if row else "GRP"


GENERADORES = [
    invictos,
    goleadores,
    partido_mas_goles,
    mejor_posesion,
    grupo_mas_goleador,
    vallas_invictas,
    racha_goleadora_jugador,
    peor_defensa,
]


def generar(cur) -> list[dict]:
    """Ejecuta todas las analíticas y devuelve las narrativas candidatas (sin persistir)."""
    edicion_id = load_edicion_id(cur)
    fase = _fase_actual(cur, edicion_id)
    multiplicador = _FASE_MULTIPLIER.get(fase, 1.0)

    candidatas = []
    for generador in GENERADORES:
        candidata = generador(cur, edicion_id)
        if candidata:
            candidata["score_relevancia"] = min(1.0, candidata["score_relevancia"] * multiplicador)
            candidatas.append(candidata)
    return candidatas
