"""
Narrativas — Cruce con histórico de Mundiales.

Compara los datos del torneo actual con `historico_resultado` y
`historico_record` para detectar conexiones con ediciones anteriores.

Misma interfaz que `analiticas.py`: cada función devuelve `None` o un dict
con `titulo`, `tipo`, `fuente_datos`, `score_relevancia`, `entidades_json`
y `contexto`.
"""

import re

from world_cup.pipelines.narrativas import analiticas


def _parse_valor_int(valor: str | None) -> int | None:
    if not valor:
        return None
    m = re.search(r"\d+", valor)
    return int(m.group()) if m else None


# ---------------------------------------------------------------------------
# Enfrentamientos históricos
# ---------------------------------------------------------------------------

def enfrentamiento_historico(cur, edicion_id: int) -> dict | None:
    cur.execute(
        """
        SELECT part.partido_id, part.fecha_hora,
               pl.nombre AS local, pv.nombre AS visitante,
               part.goles_local, part.goles_visitante,
               sl.seleccion_id AS local_seleccion_id, sv.seleccion_id AS visit_seleccion_id,
               pl.pais_id AS local_pais_id, pv.pais_id AS visit_pais_id,
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
        ORDER BY part.fecha_hora
        """,
        {"edicion_id": edicion_id},
    )
    cols = [c.name for c in cur.description]
    partidos = [dict(zip(cols, row)) for row in cur.fetchall()]

    mejor = None
    for p in partidos:
        cur.execute(
            """
            SELECT hr.pais_local_id, hr.goles_local, hr.goles_visitante, hr.fase, he.anyo
            FROM historico_resultado hr
            JOIN historico_edicion he ON he.historico_edicion_id = hr.historico_edicion_id
            WHERE (hr.pais_local_id = %(a)s AND hr.pais_visitante_id = %(b)s)
               OR (hr.pais_local_id = %(b)s AND hr.pais_visitante_id = %(a)s)
            ORDER BY he.anyo
            """,
            {"a": p["local_pais_id"], "b": p["visit_pais_id"]},
        )
        cols2 = [c.name for c in cur.description]
        previos = [dict(zip(cols2, row)) for row in cur.fetchall()]
        if previos and (mejor is None or len(previos) > len(mejor["previos"])):
            mejor = {"partido": p, "previos": previos}

    if not mejor:
        return None

    p = mejor["partido"]
    previos = mejor["previos"]

    victorias = empates = derrotas = 0
    for h in previos:
        if h["pais_local_id"] == p["local_pais_id"]:
            gf, gc = h["goles_local"], h["goles_visitante"]
        else:
            gf, gc = h["goles_visitante"], h["goles_local"]
        if gf > gc:
            victorias += 1
        elif gf == gc:
            empates += 1
        else:
            derrotas += 1

    fecha = p["fecha_hora"].date().isoformat() if p["fecha_hora"] else None

    return {
        "titulo": (
            f"{p['local']} y {p['visitante']} ya se habían enfrentado {len(previos)} "
            f"veces en Mundiales antes del {fecha}"
        ),
        "tipo": "comparativa",
        "fuente_datos": "mixta",
        "score_relevancia": min(1.0, 0.3 + 0.1 * len(previos)),
        "entidades_json": [
            {"tipo": "seleccion", "id": p["local_seleccion_id"]},
            {"tipo": "seleccion", "id": p["visit_seleccion_id"]},
            {"tipo": "partido", "id": p["partido_id"]},
        ],
        "contexto": {
            "tipo_narrativa": "enfrentamiento_historico",
            "partido_actual": {
                "local": p["local"], "visitante": p["visitante"],
                "goles_local": p["goles_local"], "goles_visitante": p["goles_visitante"],
                "fase": p["fase"], "grupo": p["grupo"], "fecha": fecha,
            },
            "historial_previo": {
                "victorias_local": victorias, "empates": empates, "derrotas_local": derrotas,
            },
            "enfrentamientos_previos": previos,
        },
    }


# ---------------------------------------------------------------------------
# Racha invicta vs récord histórico
# ---------------------------------------------------------------------------

def racha_invicta_vs_historico(cur, edicion_id: int) -> dict | None:
    actual = analiticas.invictos(cur, edicion_id)
    if not actual:
        return None

    seleccion_ids = [e["id"] for e in actual["entidades_json"] if e["tipo"] == "seleccion"]
    pj = actual["contexto"]["selecciones"][0]["partidos_jugados"]

    cur.execute(
        """
        SELECT s.seleccion_id, p.nombre, hr.valor, hr.descripcion, he.anyo
        FROM historico_record hr
        JOIN pais p ON p.pais_id = hr.pais_id
        JOIN seleccion s ON s.pais_id = p.pais_id
        LEFT JOIN historico_edicion he ON he.historico_edicion_id = hr.historico_edicion_id
        WHERE hr.tipo = 'racha_invicto' AND s.seleccion_id = ANY(%s)
        """,
        (seleccion_ids,),
    )

    mejor = None
    for seleccion_id, nombre, valor, descripcion, anyo in cur.fetchall():
        record_val = _parse_valor_int(valor)
        if record_val is None or pj < record_val:
            continue
        if mejor is None or record_val > mejor["record_val"]:
            mejor = {
                "seleccion_id": seleccion_id, "nombre": nombre, "record_val": record_val,
                "descripcion": descripcion, "anyo": anyo,
            }

    if not mejor:
        return None

    return {
        "titulo": (
            f"{mejor['nombre']} igualan o superan su racha invicta histórica en "
            f"Mundiales ({mejor['record_val']} partidos, {mejor['anyo']})"
        ),
        "tipo": "hito",
        "fuente_datos": "mixta",
        "score_relevancia": 0.7,
        "entidades_json": [{"tipo": "seleccion", "id": mejor["seleccion_id"]}],
        "contexto": {
            "tipo_narrativa": "racha_invicta_vs_historico",
            "seleccion": mejor["nombre"],
            "partidos_invicto_actual": pj,
            "record_historico": {
                "valor": mejor["record_val"], "edicion": mejor["anyo"],
                "descripcion": mejor["descripcion"],
            },
        },
    }


GENERADORES = [enfrentamiento_historico, racha_invicta_vs_historico]


def generar(cur, edicion_id: int) -> list[dict]:
    """Ejecuta los cruces con histórico y devuelve las narrativas candidatas (sin persistir)."""
    candidatas = []
    for generador in GENERADORES:
        candidata = generador(cur, edicion_id)
        if candidata:
            candidatas.append(candidata)
    return candidatas
