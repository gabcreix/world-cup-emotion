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

Idempotencia:
    El HTML generado se guarda en data/emails/YYYY-MM-DD.html. Si el
    fichero se regenera en cada ejecución. El envío del email se controla
    con data/emails/YYYY-MM-DD.sent: si existe, no se reenvía.

Solo se envía si hay partidos con estado='finalizado' en la fecha del
informe.

NOTA: esta primera versión cubre las secciones basadas en datos
(cabecera, resultados, tabla de grupos, preview del día siguiente,
estadísticas acumuladas). Las secciones con LLM (datos relevantes,
hecho histórico, noticias destacadas, sentimiento, fuera del campo,
crónica) se añaden en una segunda iteración.
"""

import argparse
import datetime
import html
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from world_cup import db

EDICION_ANYO = 2026

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
                 preview: list[dict], stats: dict | None) -> str:
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

    html_body = _build_html(fecha, resultados, tablas, preview, stats)
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
