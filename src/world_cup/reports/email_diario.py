"""
Informe diario por email — Mundial 2026.

Genera un resumen HTML de la jornada y lo envía por email.

Uso:
    python -m world_cup.reports.email_diario
    python -m world_cup.reports.email_diario --fecha 2026-06-11

Variables de entorno (.env):
    EMAIL_SENDER=tu@gmail.com
    EMAIL_PASSWORD=xxxx xxxx xxxx xxxx   # Gmail app password
    EMAIL_RECIPIENT=tu@gmail.com
    OPENAI_API_KEY=sk-...                # secciones con LLM

Idempotencia:
    El HTML generado se guarda en data/emails/YYYY-MM-DD.html. Si el
    fichero se regenera en cada ejecución. El envío del email se controla
    con data/emails/YYYY-MM-DD.sent: si existe, no se reenvía.

Solo se envía si hay partidos con estado='finalizado' en la fecha del
informe.

Secciones con LLM (datos relevantes, hecho histórico, noticias
destacadas, fuera del campo, crónica) se omiten silenciosamente si no
hay datos suficientes o si falla la llamada al modelo, para no bloquear
el envío de las secciones basadas en datos.
"""

import argparse
import datetime
import html
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from openai import OpenAI

from world_cup import db

EDICION_ANYO = 2026

MODELO_LLM = "gpt-4o-mini"
SYSTEM_PROMPT = """
Eres un periodista deportivo especializado en fútbol internacional,
escribiendo para una audiencia hispanohablante global.
Tono: analítico pero accesible, con datos concretos, en español.
Evita clichés. Sé preciso y directo.
"""

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "data" / "emails"

DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flag(codigo_iso2: str | None) -> str:
    if not codigo_iso2 or len(codigo_iso2) != 2:
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in codigo_iso2.upper())


def _fecha_larga(fecha: datetime.date) -> str:
    dia = DIAS_ES[fecha.weekday()]
    mes = MESES_ES[fecha.month - 1]
    return f"{dia.capitalize()} {fecha.day} de {mes} de {fecha.year}"


def _marcador(p: dict) -> str:
    marcador = f"{p['goles_local']} - {p['goles_visitante']}"
    if p["goles_local_prorroga"] is not None and p["goles_visit_prorroga"] is not None:
        marcador += f" ({p['goles_local_prorroga']}-{p['goles_visit_prorroga']} p.)"
    if p["penaltis_local"] is not None and p["penaltis_visitante"] is not None:
        marcador += f" — penaltis {p['penaltis_local']}-{p['penaltis_visitante']}"
    return marcador


def _llm_text(client: OpenAI, prompt: str) -> str:
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content.strip()


def _llm_json(client: OpenAI, prompt: str) -> dict:
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def _resultados_del_dia(cur, fecha: datetime.date) -> list[dict]:
    cur.execute(
        """
        SELECT
            p.partido_id, p.fecha_hora,
            f.codigo AS fase, g.letra AS grupo,
            pl.nombre AS local, sl.codigo_fifa AS local_fifa, pl.codigo_iso2 AS local_iso2,
            pv.nombre AS visitante, sv.codigo_fifa AS visit_fifa, pv.codigo_iso2 AS visit_iso2,
            p.goles_local, p.goles_visitante,
            p.goles_local_prorroga, p.goles_visit_prorroga,
            p.penaltis_local, p.penaltis_visitante,
            est.ciudad, ae.alias AS estadio_nombre,
            pal.participacion_id AS local_participacion_id,
            pav.participacion_id AS visit_participacion_id,
            sl.seleccion_id AS local_seleccion_id,
            sv.seleccion_id AS visit_seleccion_id,
            pl.pais_id AS local_pais_id,
            pv.pais_id AS visit_pais_id,
            pal.dt_id AS local_dt_id,
            pav.dt_id AS visit_dt_id
        FROM partido p
        JOIN edicion e          ON e.edicion_id = p.edicion_id AND e.anyo = %(anyo)s
        JOIN fase f             ON f.fase_id = p.fase_id
        LEFT JOIN grupo g       ON g.grupo_id = p.grupo_id
        JOIN participacion pal  ON pal.participacion_id = p.participacion_local_id
        JOIN seleccion sl       ON sl.seleccion_id = pal.seleccion_id
        JOIN pais pl            ON pl.pais_id = sl.pais_id
        JOIN participacion pav  ON pav.participacion_id = p.participacion_visit_id
        JOIN seleccion sv       ON sv.seleccion_id = pav.seleccion_id
        JOIN pais pv            ON pv.pais_id = sv.pais_id
        LEFT JOIN estadio est   ON est.estadio_id = p.estadio_id
        LEFT JOIN alias_entidad ae
               ON ae.entidad_tipo = 'estadio'
              AND ae.entidad_id = p.estadio_id
              AND ae.es_canonico = TRUE
        WHERE p.estado = 'finalizado' AND p.fecha_hora::date = %(fecha)s
        ORDER BY p.fecha_hora, p.partido_id
        """,
        {"anyo": EDICION_ANYO, "fecha": fecha},
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _preview_dia_siguiente(cur, fecha: datetime.date) -> list[dict]:
    cur.execute(
        """
        SELECT
            p.partido_id, p.fecha_hora,
            f.codigo AS fase, g.letra AS grupo,
            pl.nombre AS local, sl.codigo_fifa AS local_fifa, pl.codigo_iso2 AS local_iso2,
            pv.nombre AS visitante, sv.codigo_fifa AS visit_fifa, pv.codigo_iso2 AS visit_iso2,
            est.ciudad, ae.alias AS estadio_nombre
        FROM partido p
        JOIN edicion e          ON e.edicion_id = p.edicion_id AND e.anyo = %(anyo)s
        JOIN fase f             ON f.fase_id = p.fase_id
        LEFT JOIN grupo g       ON g.grupo_id = p.grupo_id
        JOIN participacion pal  ON pal.participacion_id = p.participacion_local_id
        JOIN seleccion sl       ON sl.seleccion_id = pal.seleccion_id
        JOIN pais pl            ON pl.pais_id = sl.pais_id
        JOIN participacion pav  ON pav.participacion_id = p.participacion_visit_id
        JOIN seleccion sv       ON sv.seleccion_id = pav.seleccion_id
        JOIN pais pv            ON pv.pais_id = sv.pais_id
        LEFT JOIN estadio est   ON est.estadio_id = p.estadio_id
        LEFT JOIN alias_entidad ae
               ON ae.entidad_tipo = 'estadio'
              AND ae.entidad_id = p.estadio_id
              AND ae.es_canonico = TRUE
        WHERE p.fecha_hora::date = %(fecha)s
        ORDER BY p.fecha_hora, p.partido_id
        """,
        {"anyo": EDICION_ANYO, "fecha": fecha + datetime.timedelta(days=1)},
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _grupos_con_partidos_hoy(cur, fecha: datetime.date) -> list[int]:
    cur.execute(
        """
        SELECT DISTINCT p.grupo_id
        FROM partido p
        JOIN fase f ON f.fase_id = p.fase_id
        WHERE f.codigo = 'GRP' AND p.estado = 'finalizado'
          AND p.fecha_hora::date = %s AND p.grupo_id IS NOT NULL
        """,
        (fecha,),
    )
    return [row[0] for row in cur.fetchall()]


def _tablas_de_grupos(cur, grupo_ids: list[int]) -> dict[str, list[dict]]:
    """Devuelve {letra_grupo: [fila_tabla, ...]} para los grupos indicados."""
    if not grupo_ids:
        return {}

    cur.execute(
        """
        SELECT pa.participacion_id, g.letra, p.nombre, s.codigo_fifa
        FROM participacion pa
        JOIN grupo g ON g.grupo_id = pa.grupo_id
        JOIN seleccion s ON s.seleccion_id = pa.seleccion_id
        JOIN pais p ON p.pais_id = s.pais_id
        WHERE pa.grupo_id = ANY(%s)
        """,
        (grupo_ids,),
    )
    equipos: dict[int, dict] = {}
    letras: dict[int, str] = {}
    for participacion_id, letra, nombre, codigo_fifa in cur.fetchall():
        letras[participacion_id] = letra
        equipos[participacion_id] = {
            "letra": letra, "nombre": nombre, "codigo_fifa": codigo_fifa,
            "pj": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0,
        }

    cur.execute(
        """
        SELECT p.participacion_local_id, p.participacion_visit_id,
               p.goles_local, p.goles_visitante
        FROM partido p
        JOIN fase f ON f.fase_id = p.fase_id
        WHERE f.codigo = 'GRP' AND p.estado = 'finalizado'
          AND p.grupo_id = ANY(%s)
        """,
        (grupo_ids,),
    )
    for local_id, visit_id, gl, gv in cur.fetchall():
        if local_id in equipos and visit_id in equipos:
            for pid, gf, gc in ((local_id, gl, gv), (visit_id, gv, gl)):
                eq = equipos[pid]
                eq["pj"] += 1
                eq["gf"] += gf
                eq["gc"] += gc
                if gf > gc:
                    eq["g"] += 1
                elif gf == gc:
                    eq["e"] += 1
                else:
                    eq["p"] += 1

    tablas: dict[str, list[dict]] = {}
    for eq in equipos.values():
        eq["dg"] = eq["gf"] - eq["gc"]
        eq["pts"] = eq["g"] * 3 + eq["e"]
        tablas.setdefault(eq["letra"], []).append(eq)

    for letra, filas in tablas.items():
        filas.sort(key=lambda r: (-r["pts"], -r["dg"], -r["gf"], r["nombre"]))

    return dict(sorted(tablas.items()))


def _stats_acumuladas(cur) -> dict | None:
    cur.execute(
        """
        SELECT
            COUNT(*) AS partidos,
            COALESCE(SUM(goles_local + goles_visitante), 0) AS goles_totales
        FROM partido
        WHERE estado = 'finalizado'
        """
    )
    partidos, goles_totales = cur.fetchone()
    if not partidos:
        return None

    cur.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE tipo = 'tarjeta_amarilla') AS amarillas,
            COUNT(*) FILTER (WHERE tipo IN ('tarjeta_roja', 'doble_amarilla')) AS rojas,
            COUNT(*) FILTER (WHERE tipo = 'gol_penalti') AS penaltis,
            COUNT(*) FILTER (WHERE tipo = 'gol_propia') AS autogoles
        FROM evento_partido
        """
    )
    amarillas, rojas, penaltis, autogoles = cur.fetchone()

    return {
        "partidos": partidos,
        "goles_totales": goles_totales,
        "media_goles": goles_totales / partidos,
        "amarillas": amarillas,
        "rojas": rojas,
        "penaltis": penaltis,
        "autogoles": autogoles,
    }


def _equipos_jugaron_hoy(cur, resultados: list[dict]) -> dict:
    """Identidades de las selecciones/jugadores/DTs que jugaron hoy, para filtrar noticias."""
    participacion_ids: list[int] = []
    seleccion_ids: list[int] = []
    pais_ids: list[int] = []
    dt_ids: list[int] = []
    partido_ids: list[int] = []

    for p in resultados:
        participacion_ids += [p["local_participacion_id"], p["visit_participacion_id"]]
        seleccion_ids += [p["local_seleccion_id"], p["visit_seleccion_id"]]
        pais_ids += [p["local_pais_id"], p["visit_pais_id"]]
        partido_ids.append(p["partido_id"])
        for dt_id in (p["local_dt_id"], p["visit_dt_id"]):
            if dt_id is not None:
                dt_ids.append(dt_id)

    cur.execute(
        "SELECT jugador_id FROM convocatoria WHERE participacion_id = ANY(%s)",
        (participacion_ids,),
    )
    jugador_ids = [row[0] for row in cur.fetchall()]

    return {
        "participacion_ids": participacion_ids,
        "seleccion_ids": seleccion_ids,
        "pais_ids": pais_ids,
        "dt_ids": dt_ids,
        "jugador_ids": jugador_ids,
        "partido_ids": partido_ids,
    }


# ---------------------------------------------------------------------------
# Datos relevantes del día (sección 4 — LLM)
# ---------------------------------------------------------------------------

def _datos_relevantes_partido(cur, partido_ids: list[int]) -> dict | None:
    """Recopila goleadores, stats destacadas y stats de equipo de los partidos de hoy."""
    if not partido_ids:
        return None

    cur.execute(
        """
        SELECT se.partido_id, p.nombre AS pais, se.xg, se.posesion,
               se.tiros_totales, se.tiros_a_puerta, se.pases_completados, se.pases_totales,
               se.corners, se.fueras_de_juego, se.faltas_cometidas
        FROM stats_equipo se
        JOIN participacion pa ON pa.participacion_id = se.participacion_id
        JOIN seleccion s ON s.seleccion_id = pa.seleccion_id
        JOIN pais p ON p.pais_id = s.pais_id
        WHERE se.partido_id = ANY(%s)
        """,
        (partido_ids,),
    )
    cols = [c.name for c in cur.description]
    stats_equipo = [dict(zip(cols, row)) for row in cur.fetchall()]
    if not stats_equipo:
        return None

    cur.execute(
        """
        SELECT e.partido_id, e.tipo, e.minuto, e.minuto_adicional,
               j.nombre_completo AS jugador, p.nombre AS pais
        FROM evento_partido e
        JOIN jugador j ON j.jugador_id = e.jugador_id
        JOIN participacion pa ON pa.participacion_id = e.participacion_id
        JOIN seleccion s ON s.seleccion_id = pa.seleccion_id
        JOIN pais p ON p.pais_id = s.pais_id
        WHERE e.partido_id = ANY(%s) AND e.tipo IN ('gol', 'gol_penalti', 'gol_propia')
        ORDER BY e.partido_id, e.minuto
        """,
        (partido_ids,),
    )
    cols = [c.name for c in cur.description]
    goles = [dict(zip(cols, row)) for row in cur.fetchall()]

    cur.execute(
        """
        SELECT sj.partido_id, j.nombre_completo AS jugador, p.nombre AS pais,
               sj.nota, sj.minutos_jugados, sj.stats_extra_json,
               j.posicion AS posicion_jugador
        FROM stats_jugador sj
        JOIN jugador j ON j.jugador_id = sj.jugador_id
        JOIN participacion pa ON pa.participacion_id = sj.participacion_id
        JOIN seleccion s ON s.seleccion_id = pa.seleccion_id
        JOIN pais p ON p.pais_id = s.pais_id
        WHERE sj.partido_id = ANY(%s) AND sj.nota IS NOT NULL
        ORDER BY sj.nota DESC
        LIMIT 8
        """,
        (partido_ids,),
    )
    cols = [c.name for c in cur.description]
    destacados = [dict(zip(cols, row)) for row in cur.fetchall()]

    return {
        "stats_equipo": stats_equipo,
        "goles": goles,
        "jugadores_destacados": destacados,
    }


def _render_datos_relevantes(client: OpenAI, datos: dict | None) -> str:
    if not datos:
        return ""

    payload = json.dumps(datos, default=str, ensure_ascii=False)
    prompt = (
        "A partir de estos datos en JSON de los partidos del Mundial 2026 jugados hoy "
        "(stats de equipo, goles y jugadores más destacados por nota), redacta un breve "
        "apartado en HTML titulado 'Datos relevantes del día'. Destaca a los goleadores, "
        "al jugador con mejor nota (portero o no) y una estadística curiosa (posesión, "
        "tiros, xG, etc.). Usa una lista <ul><li> con 3-5 puntos, sin introducción ni "
        "encabezado <h2>. No inventes datos que no estén en el JSON.\n\n"
        f"Datos:\n{payload}"
    )

    try:
        cuerpo = _llm_text(client, prompt)
    except Exception as exc:
        print(f"[WARN] Sección 'Datos relevantes' omitida (error LLM): {exc}")
        return ""

    return f"<h2>📊 Datos relevantes del día</h2>{cuerpo}"


# ---------------------------------------------------------------------------
# Hecho histórico del día (sección 5 — LLM)
# ---------------------------------------------------------------------------

def _hecho_historico(cur, resultados: list[dict]) -> dict | None:
    """Busca precedentes históricos para los emparejamientos de hoy."""
    precedentes = []
    pais_ids: set[int] = set()

    for p in resultados:
        local_id, visit_id = p["local_pais_id"], p["visit_pais_id"]
        pais_ids.update({local_id, visit_id})
        cur.execute(
            """
            SELECT hr.fase, pl.nombre AS local, pv.nombre AS visitante,
                   hr.goles_local, hr.goles_visitante,
                   hr.goles_local_prorroga, hr.goles_visit_prorroga,
                   hr.penaltis_local, hr.penaltis_visitante,
                   hr.fecha, he.anyo
            FROM historico_resultado hr
            JOIN historico_edicion he ON he.historico_edicion_id = hr.historico_edicion_id
            JOIN pais pl ON pl.pais_id = hr.pais_local_id
            JOIN pais pv ON pv.pais_id = hr.pais_visitante_id
            WHERE (hr.pais_local_id = %(local)s AND hr.pais_visitante_id = %(visit)s)
               OR (hr.pais_local_id = %(visit)s AND hr.pais_visitante_id = %(local)s)
            ORDER BY he.anyo
            """,
            {"local": local_id, "visit": visit_id},
        )
        cols = [c.name for c in cur.description]
        enfrentamientos = [dict(zip(cols, row)) for row in cur.fetchall()]
        if enfrentamientos:
            precedentes.append({
                "local_hoy": p["local"],
                "visitante_hoy": p["visitante"],
                "resultado_hoy": _marcador(p),
                "enfrentamientos_previos": enfrentamientos,
            })

    if not pais_ids:
        return None

    cur.execute(
        """
        SELECT hr.tipo, hr.valor, hr.descripcion, p.nombre AS pais, he.anyo
        FROM historico_record hr
        LEFT JOIN pais p ON p.pais_id = hr.pais_id
        LEFT JOIN historico_edicion he ON he.historico_edicion_id = hr.historico_edicion_id
        WHERE hr.pais_id = ANY(%s)
        """,
        (list(pais_ids),),
    )
    cols = [c.name for c in cur.description]
    records = [dict(zip(cols, row)) for row in cur.fetchall()]

    if not precedentes and not records:
        return None

    return {"precedentes": precedentes, "records": records}


def _render_hecho_historico(client: OpenAI, datos: dict | None) -> str:
    if not datos:
        return ""

    payload = json.dumps(datos, default=str, ensure_ascii=False)
    prompt = (
        "A partir de estos datos en JSON sobre precedentes históricos de Mundiales "
        "para los partidos de hoy del Mundial 2026, escribe UNA sola frase en español "
        "que conecte el resultado de hoy con ese histórico (un enfrentamiento previo "
        "destacado o un récord relevante). Si nada resulta realmente interesante, "
        "responde exactamente con la palabra OMITIR. Devuelve solo la frase (o "
        "'OMITIR'), sin comillas ni etiquetas HTML.\n\n"
        f"Datos:\n{payload}"
    )

    try:
        frase = _llm_text(client, prompt)
    except Exception as exc:
        print(f"[WARN] Sección 'Hecho histórico' omitida (error LLM): {exc}")
        return ""

    if not frase or frase.strip().upper().startswith("OMITIR"):
        return ""

    return f"<h2>📜 Hecho histórico del día</h2><p>{html.escape(frase)}</p>"


# ---------------------------------------------------------------------------
# Noticias destacadas (sección 6 — LLM para la intro)
# ---------------------------------------------------------------------------

def _noticias_destacadas(cur, fecha: datetime.date, equipos: dict) -> list[dict]:
    cur.execute(
        """
        SELECT DISTINCT n.noticia_id, n.titulo, n.url, n.resumen, n.relevancia,
               n.fecha_ingestion, f.nombre AS fuente_nombre
        FROM noticia n
        JOIN fuente f ON f.fuente_id = n.fuente_id
        JOIN mencion m ON m.noticia_id = n.noticia_id
        WHERE n.fecha_ingestion::date = %(fecha)s
          AND (
                (m.entidad_tipo = 'seleccion' AND m.entidad_id = ANY(%(seleccion_ids)s))
             OR (m.entidad_tipo = 'jugador'   AND m.entidad_id = ANY(%(jugador_ids)s))
             OR (m.entidad_tipo = 'dt'        AND m.entidad_id = ANY(%(dt_ids)s))
             OR (m.entidad_tipo = 'partido'   AND m.entidad_id = ANY(%(partido_ids)s))
          )
        ORDER BY n.relevancia DESC NULLS LAST, n.fecha_ingestion DESC
        LIMIT 10
        """,
        {
            "fecha": fecha,
            "seleccion_ids": equipos["seleccion_ids"],
            "jugador_ids": equipos["jugador_ids"],
            "dt_ids": equipos["dt_ids"],
            "partido_ids": equipos["partido_ids"],
        },
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _render_noticias_destacadas(client: OpenAI, noticias: list[dict]) -> str:
    if not noticias:
        return ""

    titulos = [n["titulo"] for n in noticias]
    prompt = (
        "Aquí tienes los titulares de las noticias más destacadas de hoy sobre el "
        "Mundial 2026, relacionadas con los equipos que han jugado:\n\n"
        + "\n".join(f"- {t}" for t in titulos)
        + "\n\nEscribe un párrafo introductorio breve (2-3 frases) en español que "
        "resuma de qué hablan estas noticias, sin enumerar cada titular literalmente. "
        "Devuelve solo el texto del párrafo, sin etiquetas HTML."
    )

    try:
        intro = _llm_text(client, prompt)
    except Exception as exc:
        print(f"[WARN] Sección 'Noticias destacadas' sin intro (error LLM): {exc}")
        intro = ""

    filas = []
    for n in noticias:
        titulo = html.escape(n["titulo"])
        url = html.escape(n["url"], quote=True)
        fuente = html.escape(n["fuente_nombre"])
        filas.append(
            f'<li><a href="{url}" target="_blank">{titulo}</a> '
            f'<span class="meta-fuente">— {fuente}</span></li>'
        )

    intro_html = f"<p>{html.escape(intro)}</p>" if intro else ""
    return f"<h2>📰 Noticias destacadas</h2>{intro_html}<ul class=\"noticias\">{''.join(filas)}</ul>"


# ---------------------------------------------------------------------------
# Sentimiento de prensa (sección 7 — datos, sin LLM)
# ---------------------------------------------------------------------------

def _sentimiento_prensa(cur, equipos: dict) -> list[dict]:
    if not equipos["seleccion_ids"]:
        return []

    cur.execute(
        """
        SELECT p.nombre AS pais, p.codigo_iso2,
               COUNT(*) FILTER (WHERE m.sentimiento = 'positivo') AS positivas,
               COUNT(*) FILTER (WHERE m.sentimiento = 'negativo') AS negativas,
               COUNT(*) FILTER (WHERE m.sentimiento = 'neutro')   AS neutras,
               COUNT(*) AS total
        FROM mencion m
        JOIN noticia n ON n.noticia_id = m.noticia_id
        JOIN seleccion s ON s.seleccion_id = m.entidad_id
        JOIN pais p ON p.pais_id = s.pais_id
        WHERE m.entidad_tipo = 'seleccion'
          AND m.entidad_id = ANY(%s)
          AND m.sentimiento IS NOT NULL
          AND n.fecha_ingestion >= NOW() - INTERVAL '24 hours'
        GROUP BY p.nombre, p.codigo_iso2
        ORDER BY total DESC
        """,
        (equipos["seleccion_ids"],),
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _render_sentimiento_prensa(sentimiento: list[dict]) -> str:
    if not sentimiento:
        return ""

    filas = []
    for s in sentimiento:
        conteos = {"positivo": s["positivas"], "negativo": s["negativas"], "neutro": s["neutras"]}
        dominante = max(conteos, key=conteos.get)
        emoji = {"positivo": "🟢", "negativo": "🔴", "neutro": "⚪"}[dominante]
        filas.append(
            f"<tr><td class=\"equipo\">{_flag(s['codigo_iso2'])} {html.escape(s['pais'])}</td>"
            f"<td class=\"tono\">{emoji}</td>"
            f"<td class=\"meta\">{s['total']} mención{'es' if s['total'] != 1 else ''}</td></tr>"
        )

    return f"""
    <h2>🗞️ Sentimiento de prensa</h2>
    <table class="sentimiento">
      {''.join(filas)}
    </table>
    """


# ---------------------------------------------------------------------------
# Lo más destacado fuera del campo (sección 8 — LLM)
# ---------------------------------------------------------------------------

def _noticias_fuera_de_campo(cur, fecha: datetime.date, equipos: dict) -> list[dict]:
    cur.execute(
        """
        SELECT n.noticia_id, n.titulo, n.url, n.resumen, f.nombre AS fuente_nombre
        FROM noticia n
        JOIN fuente f ON f.fuente_id = n.fuente_id
        WHERE n.fecha_ingestion::date = %(fecha)s
          AND NOT EXISTS (
              SELECT 1 FROM mencion m
              WHERE m.noticia_id = n.noticia_id
                AND (
                      (m.entidad_tipo = 'seleccion' AND m.entidad_id = ANY(%(seleccion_ids)s))
                   OR (m.entidad_tipo = 'partido'   AND m.entidad_id = ANY(%(partido_ids)s))
                )
          )
        ORDER BY n.relevancia DESC NULLS LAST, n.fecha_ingestion DESC
        LIMIT 15
        """,
        {
            "fecha": fecha,
            "seleccion_ids": equipos["seleccion_ids"],
            "partido_ids": equipos["partido_ids"],
        },
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _render_fuera_de_campo(client: OpenAI, noticias: list[dict]) -> str:
    if not noticias:
        return ""

    items = [{"id": n["noticia_id"], "titulo": n["titulo"], "resumen": n["resumen"]} for n in noticias]
    prompt = (
        "A partir de esta lista de noticias en JSON sobre el Mundial 2026 (no "
        "relacionadas directamente con los partidos de hoy), elige las 3 o 4 más "
        "interesantes para una sección 'Lo más destacado fuera del campo' (lesiones, "
        "polémicas, historias humanas, etc.) y escribe para cada una un comentario "
        "breve de 1-2 frases en español. Devuelve SOLO un JSON con este formato: "
        '{"items": [{"id": <id>, "comentario": "<texto>"}, ...]}\n\n'
        f"Noticias:\n{json.dumps(items, default=str, ensure_ascii=False)}"
    )

    try:
        data = _llm_json(client, prompt)
    except Exception as exc:
        print(f"[WARN] Sección 'Fuera del campo' omitida (error LLM): {exc}")
        return ""

    by_id = {n["noticia_id"]: n for n in noticias}
    filas = []
    for item in data.get("items", []):
        n = by_id.get(item.get("id"))
        if not n:
            continue
        titulo = html.escape(n["titulo"])
        url = html.escape(n["url"], quote=True)
        comentario = html.escape(item.get("comentario", ""))
        filas.append(
            f'<li><a href="{url}" target="_blank">{titulo}</a><br>'
            f'<span class="comentario">{comentario}</span></li>'
        )

    if not filas:
        return ""

    return f"<h2>🌍 Lo más destacado fuera del campo</h2><ul class=\"fuera-campo\">{''.join(filas)}</ul>"


# ---------------------------------------------------------------------------
# Crónica del día (sección 9 — LLM)
# ---------------------------------------------------------------------------

def _render_cronica(client: OpenAI, fecha: datetime.date, resultados: list[dict],
                     tablas: dict[str, list[dict]], stats: dict | None) -> str:
    resumen = {
        "fecha": fecha.isoformat(),
        "resultados": [
            {
                "local": p["local"], "visitante": p["visitante"],
                "marcador": _marcador(p), "fase": p["fase"], "grupo": p["grupo"],
            }
            for p in resultados
        ],
        "tablas_grupos": tablas,
        "stats_acumuladas": stats,
    }

    prompt = (
        "A partir de estos datos en JSON sobre la jornada de hoy del Mundial 2026, "
        "escribe una crónica de 150-200 palabras en español, con tono periodístico. "
        "Cuenta qué fue lo más importante de la jornada, qué sorprendió y qué historia "
        "define el día. Devuelve solo el texto de la crónica en párrafos (puedes usar "
        "etiquetas <p>), sin encabezado ni título.\n\n"
        f"Datos:\n{json.dumps(resumen, default=str, ensure_ascii=False)}"
    )

    try:
        cuerpo = _llm_text(client, prompt)
    except Exception as exc:
        print(f"[WARN] Sección 'Crónica del día' omitida (error LLM): {exc}")
        return ""

    return f"<h2>✍️ Crónica del día</h2>{cuerpo}"


# ---------------------------------------------------------------------------
# Render HTML
# ---------------------------------------------------------------------------

def _render_resultados(resultados: list[dict]) -> str:
    if not resultados:
        return ""

    filas = []
    for p in resultados:
        hora = p["fecha_hora"].strftime("%H:%M") if p["fecha_hora"] else ""
        fase = f"{p['fase']}" + (f" · Grupo {p['grupo']}" if p["grupo"] else "")
        estadio = p["estadio_nombre"] or p["ciudad"] or ""
        ciudad = p["ciudad"] or ""
        sede = f"{estadio} — {ciudad}" if estadio and ciudad and estadio != ciudad else (estadio or ciudad)

        filas.append(f"""
        <tr>
          <td class="hora">{hora}</td>
          <td class="equipo">{_flag(p['local_iso2'])} {html.escape(p['local'])}</td>
          <td class="marcador">{_marcador(p)}</td>
          <td class="equipo">{html.escape(p['visitante'])} {_flag(p['visit_iso2'])}</td>
          <td class="meta">{html.escape(fase)}<br><span class="sede">{html.escape(sede)}</span></td>
        </tr>
        """)

    return f"""
    <h2>⚽ Resultados del día</h2>
    <table class="resultados">
      {''.join(filas)}
    </table>
    """


def _render_tablas_grupos(tablas: dict[str, list[dict]]) -> str:
    if not tablas:
        return ""

    bloques = []
    for letra, filas in tablas.items():
        rows = "".join(
            f"<tr><td>{i + 1}</td><td>{html.escape(r['nombre'])}</td>"
            f"<td>{r['pj']}</td><td>{r['g']}</td><td>{r['e']}</td><td>{r['p']}</td>"
            f"<td>{r['gf']}</td><td>{r['gc']}</td><td>{r['dg']:+d}</td><td><b>{r['pts']}</b></td></tr>"
            for i, r in enumerate(filas)
        )
        bloques.append(f"""
        <h3>Grupo {letra}</h3>
        <table class="grupo">
          <thead><tr><th>Pos</th><th>Selección</th><th>PJ</th><th>G</th><th>E</th>
          <th>P</th><th>GF</th><th>GC</th><th>DG</th><th>Pts</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
        """)

    return f"<h2>📊 Tabla de grupos actualizada</h2>{''.join(bloques)}"


def _render_preview(preview: list[dict], fecha: datetime.date) -> str:
    if not preview:
        return ""

    fecha_siguiente = _fecha_larga(fecha + datetime.timedelta(days=1))
    filas = []
    for p in preview:
        hora = p["fecha_hora"].strftime("%H:%M") if p["fecha_hora"] else ""
        fase = f"{p['fase']}" + (f" · Grupo {p['grupo']}" if p["grupo"] else "")
        estadio = p["estadio_nombre"] or p["ciudad"] or ""
        ciudad = p["ciudad"] or ""
        sede = f"{estadio} — {ciudad}" if estadio and ciudad and estadio != ciudad else (estadio or ciudad)

        filas.append(f"""
        <tr>
          <td class="hora">{hora}</td>
          <td class="equipo">{_flag(p['local_iso2'])} {html.escape(p['local'])}</td>
          <td class="vs">vs</td>
          <td class="equipo">{html.escape(p['visitante'])} {_flag(p['visit_iso2'])}</td>
          <td class="meta">{html.escape(fase)}<br><span class="sede">{html.escape(sede)}</span></td>
        </tr>
        """)

    return f"""
    <h2>📅 Mañana — {html.escape(fecha_siguiente)}</h2>
    <table class="resultados">
      {''.join(filas)}
    </table>
    """


def _render_stats_acumuladas(stats: dict | None) -> str:
    if not stats:
        return ""

    return f"""
    <h2>📈 Estadísticas acumuladas del torneo</h2>
    <table class="stats">
      <tr><td>Partidos jugados</td><td><b>{stats['partidos']}</b></td></tr>
      <tr><td>Goles totales</td><td><b>{stats['goles_totales']}</b></td></tr>
      <tr><td>Media de goles por partido</td><td><b>{stats['media_goles']:.2f}</b></td></tr>
      <tr><td>Tarjetas amarillas</td><td><b>{stats['amarillas']}</b></td></tr>
      <tr><td>Tarjetas rojas</td><td><b>{stats['rojas']}</b></td></tr>
      <tr><td>Goles de penalti</td><td><b>{stats['penaltis']}</b></td></tr>
      <tr><td>Autogoles</td><td><b>{stats['autogoles']}</b></td></tr>
    </table>
    """


def _build_html(fecha: datetime.date, resultados: list[dict], tablas: dict[str, list[dict]],
                 preview: list[dict], stats: dict | None, datos_relevantes: str,
                 hecho_historico: str, noticias_destacadas: str, sentimiento_prensa: str,
                 fuera_de_campo: str, cronica: str) -> str:
    fecha_larga = _fecha_larga(fecha)
    num_partidos = len(resultados)
    fases = sorted({r["fase"] for r in resultados})
    subtitulo = (
        f"{num_partidos} partido{'s' if num_partidos != 1 else ''} finalizado"
        f"{'s' if num_partidos != 1 else ''}"
        + (f" · Fase: {', '.join(fases)}" if fases else "")
    )

    secciones = "".join(filter(None, [
        _render_resultados(resultados),
        _render_tablas_grupos(tablas),
        datos_relevantes,
        hecho_historico,
        noticias_destacadas,
        sentimiento_prensa,
        fuera_de_campo,
        cronica,
        _render_preview(preview, fecha),
        _render_stats_acumuladas(stats),
    ]))

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Mundial 2026 — {fecha.isoformat()}</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 0;
         background: #f4f6f9; color: #1a1a1a; }}
  .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; padding: 1.5rem; }}
  h1 {{ margin: 0 0 0.2rem; font-size: 1.4rem; }}
  .subtitle {{ color: #666; margin: 0 0 1.2rem; font-size: 0.9rem; }}
  h2 {{ font-size: 1.05rem; margin: 1.6rem 0 0.6rem; color: #1d3461; }}
  h3 {{ font-size: 0.95rem; margin: 1rem 0 0.4rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; margin-bottom: 0.6rem; }}
  table.resultados td {{ padding: 6px 4px; border-bottom: 1px solid #eee; vertical-align: middle; }}
  table.resultados .hora {{ color: #999; width: 3.5em; }}
  table.resultados .marcador {{ font-weight: 700; text-align: center; white-space: nowrap; }}
  table.resultados .vs {{ color: #999; text-align: center; }}
  table.resultados .equipo {{ font-weight: 600; }}
  table.resultados .meta {{ color: #888; font-size: 0.75rem; text-align: right; }}
  table.resultados .sede {{ color: #aaa; }}
  table.grupo th, table.grupo td {{ border: 1px solid #eee; padding: 4px 6px; text-align: center; }}
  table.grupo th {{ background: #f0f4ff; }}
  table.grupo td:nth-child(2) {{ text-align: left; }}
  table.stats td {{ padding: 4px 0; border-bottom: 1px solid #eee; }}
  table.stats td:last-child {{ text-align: right; }}
  table.sentimiento td {{ padding: 6px 4px; border-bottom: 1px solid #eee; }}
  table.sentimiento .equipo {{ font-weight: 600; }}
  table.sentimiento .tono {{ text-align: center; width: 2.5em; }}
  table.sentimiento .meta {{ color: #888; font-size: 0.75rem; text-align: right; }}
  ul.noticias, ul.fuera-campo {{ padding-left: 1.2rem; margin: 0 0 0.6rem; }}
  ul.noticias li, ul.fuera-campo li {{ margin-bottom: 0.5rem; font-size: 0.9rem; }}
  .meta-fuente {{ color: #999; font-size: 0.8rem; }}
  .comentario {{ color: #555; font-size: 0.85rem; }}
</style>
</head>
<body>
  <div class="container">
    <h1>🏆 Mundial 2026 — {html.escape(fecha_larga)}</h1>
    <p class="subtitle">{html.escape(subtitulo)}</p>
    {secciones}
  </div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Envío
# ---------------------------------------------------------------------------

def _enviar_email(fecha: datetime.date, html_body: str) -> None:
    sender = os.environ["EMAIL_SENDER"]
    password = os.environ["EMAIL_PASSWORD"]
    recipient = os.environ["EMAIL_RECIPIENT"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Mundial 2026 — {_fecha_larga(fecha)}"
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run(fecha: datetime.date | None = None, enviar: bool = True) -> Path | None:
    fecha = fecha or datetime.date.today()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / f"{fecha.isoformat()}.html"
    sent_marker = OUT_DIR / f"{fecha.isoformat()}.sent"

    client = OpenAI()

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            resultados = _resultados_del_dia(cur, fecha)
            if not resultados:
                print(f"[INFO] Sin partidos finalizados el {fecha.isoformat()} — no se genera informe.")
                return None

            grupo_ids = _grupos_con_partidos_hoy(cur, fecha)
            tablas = _tablas_de_grupos(cur, grupo_ids)
            preview = _preview_dia_siguiente(cur, fecha)
            stats = _stats_acumuladas(cur)

            equipos = _equipos_jugaron_hoy(cur, resultados)
            partido_ids = equipos["partido_ids"]

            datos_relevantes_raw = _datos_relevantes_partido(cur, partido_ids)
            hecho_historico_raw = _hecho_historico(cur, resultados)
            noticias_destacadas_raw = _noticias_destacadas(cur, fecha, equipos)
            sentimiento_raw = _sentimiento_prensa(cur, equipos)
            fuera_de_campo_raw = _noticias_fuera_de_campo(cur, fecha, equipos)

    datos_relevantes = _render_datos_relevantes(client, datos_relevantes_raw)
    hecho_historico = _render_hecho_historico(client, hecho_historico_raw)
    noticias_destacadas = _render_noticias_destacadas(client, noticias_destacadas_raw)
    sentimiento_prensa = _render_sentimiento_prensa(sentimiento_raw)
    fuera_de_campo = _render_fuera_de_campo(client, fuera_de_campo_raw)
    cronica = _render_cronica(client, fecha, resultados, tablas, stats)

    html_body = _build_html(
        fecha, resultados, tablas, preview, stats,
        datos_relevantes, hecho_historico, noticias_destacadas,
        sentimiento_prensa, fuera_de_campo, cronica,
    )
    out_file.write_text(html_body, encoding="utf-8")
    print(f"  Informe generado: {out_file}")

    if enviar:
        if sent_marker.exists():
            print(f"[INFO] {sent_marker} ya existe — email no reenviado.")
        else:
            _enviar_email(fecha, html_body)
            sent_marker.write_text("", encoding="utf-8")
            print(f"  [EMAIL] Enviado a {os.environ.get('EMAIL_RECIPIENT')}")

    return out_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fecha", help="YYYY-MM-DD (por defecto, hoy)")
    parser.add_argument("--no-enviar", action="store_true", help="Generar el HTML sin enviar el email")
    args = parser.parse_args()

    fecha = datetime.date.fromisoformat(args.fecha) if args.fecha else None
    run(fecha=fecha, enviar=not args.no_enviar)


if __name__ == "__main__":
    main()
