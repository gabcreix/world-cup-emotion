"""
Reporte HTML — Capa gold de fbref_fixtures.

Genera data/reports/gold_fixtures.html con:
    - Calendario completo (fecha, fase, grupo, equipos, marcador, sede)
    - Resumen por grupo (fase de grupos)
    - Validaciones (partidos sin sede, fase de grupos sin grupo, etc.)

Uso:
    python -m world_cup.reports.gold_fixtures
"""

import html
from pathlib import Path

from world_cup import db

EDICION_ANYO = 2026

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "data" / "reports"
OUT_FILE = OUT_DIR / "gold_fixtures.html"


def _calendario(cur) -> list[dict]:
    cur.execute(
        """
        SELECT
            p.partido_id,
            p.fecha_hora,
            f.codigo AS fase,
            g.letra AS grupo,
            pl.nombre AS local, sl.codigo_fifa AS local_fifa,
            pv.nombre AS visitante, sv.codigo_fifa AS visit_fifa,
            p.goles_local, p.goles_visitante, p.estado,
            ae.alias AS estadio
        FROM partido p
        JOIN edicion e          ON e.edicion_id = p.edicion_id AND e.anyo = %s
        JOIN fase f             ON f.fase_id = p.fase_id
        LEFT JOIN grupo g       ON g.grupo_id = p.grupo_id
        JOIN participacion pal  ON pal.participacion_id = p.participacion_local_id
        JOIN seleccion sl       ON sl.seleccion_id = pal.seleccion_id
        JOIN pais pl            ON pl.pais_id = sl.pais_id
        JOIN participacion pav  ON pav.participacion_id = p.participacion_visit_id
        JOIN seleccion sv       ON sv.seleccion_id = pav.seleccion_id
        JOIN pais pv            ON pv.pais_id = sv.pais_id
        LEFT JOIN alias_entidad ae
               ON ae.entidad_tipo = 'estadio'
              AND ae.entidad_id = p.estadio_id
              AND ae.es_canonico = TRUE
        ORDER BY p.fecha_hora, p.partido_id
        """,
        (EDICION_ANYO,),
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _validaciones(cur) -> list[str]:
    avisos: list[str] = []

    cur.execute(
        """
        SELECT COUNT(*)
        FROM partido p
        JOIN edicion e ON e.edicion_id = p.edicion_id AND e.anyo = %s
        WHERE p.estadio_id IS NULL
        """,
        (EDICION_ANYO,),
    )
    sin_estadio = cur.fetchone()[0]
    if sin_estadio:
        avisos.append(f"Partidos sin estadio asignado: {sin_estadio}")

    cur.execute(
        """
        SELECT COUNT(*)
        FROM partido p
        JOIN edicion e ON e.edicion_id = p.edicion_id AND e.anyo = %s
        JOIN fase f    ON f.fase_id = p.fase_id
        WHERE f.codigo = 'GRP' AND p.grupo_id IS NULL
        """,
        (EDICION_ANYO,),
    )
    sin_grupo = cur.fetchone()[0]
    if sin_grupo:
        avisos.append(f"Partidos de fase de grupos sin grupo asignado: {sin_grupo}")

    cur.execute(
        """
        SELECT f.codigo, COUNT(*), f.num_partidos
        FROM partido p
        JOIN edicion e ON e.edicion_id = p.edicion_id AND e.anyo = %s
        JOIN fase f    ON f.fase_id = p.fase_id
        GROUP BY f.codigo, f.num_partidos
        ORDER BY f.codigo
        """,
        (EDICION_ANYO,),
    )
    for codigo, count, esperado in cur.fetchall():
        if esperado is not None and count != esperado:
            avisos.append(f"Fase {codigo}: {count} partidos cargados (esperados {esperado})")

    return avisos


def _build_html(calendario: list[dict], avisos: list[str]) -> str:
    total = len(calendario)
    finalizados = sum(1 for p in calendario if p["estado"] == "finalizado")

    avisos_html = (
        "".join(f"<li>{html.escape(a)}</li>" for a in avisos)
        if avisos
        else "<li>Sin incidencias detectadas.</li>"
    )

    # Resumen por grupo
    grupos: dict[str, list[dict]] = {}
    for p in calendario:
        if p["fase"] == "GRP" and p["grupo"]:
            grupos.setdefault(p["grupo"], []).append(p)

    grupos_html = ""
    for letra in sorted(grupos):
        filas = "".join(
            f"<tr>"
            f"<td>{p['fecha_hora'] or '—'}</td>"
            f"<td>{html.escape(p['local'])} ({p['local_fifa']})</td>"
            f"<td>{p['goles_local'] if p['goles_local'] is not None else '–'}"
            f" - {p['goles_visitante'] if p['goles_visitante'] is not None else '–'}</td>"
            f"<td>{html.escape(p['visitante'])} ({p['visit_fifa']})</td>"
            f"<td>{html.escape(p['estadio'] or '—')}</td>"
            f"<td>{p['estado']}</td>"
            f"</tr>"
            for p in grupos[letra]
        )
        grupos_html += f"""
        <details>
          <summary>Grupo {letra} — {len(grupos[letra])} partidos</summary>
          <table>
            <thead>
              <tr><th>Fecha</th><th>Local</th><th>Marcador</th><th>Visitante</th><th>Estadio</th><th>Estado</th></tr>
            </thead>
            <tbody>{filas}</tbody>
          </table>
        </details>
        """

    # Calendario completo
    calendario_rows = "".join(
        f"<tr>"
        f"<td>{p['fecha_hora'] or '—'}</td>"
        f"<td>{p['fase']}</td>"
        f"<td>{p['grupo'] or '—'}</td>"
        f"<td>{html.escape(p['local'])} ({p['local_fifa']})</td>"
        f"<td>{p['goles_local'] if p['goles_local'] is not None else '–'}"
        f" - {p['goles_visitante'] if p['goles_visitante'] is not None else '–'}</td>"
        f"<td>{html.escape(p['visitante'])} ({p['visit_fifa']})</td>"
        f"<td>{html.escape(p['estadio'] or '—')}</td>"
        f"<td>{p['estado']}</td>"
        f"</tr>"
        for p in calendario
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Gold — fbref_fixtures ({EDICION_ANYO})</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; }}
  h1 {{ margin-bottom: 0.2rem; }}
  .subtitle {{ color: #666; margin-top: 0; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 1rem; }}
  th, td {{ border: 1px solid #ddd; padding: 4px 8px; text-align: left; font-size: 0.9rem; }}
  th {{ background: #f4f4f4; position: sticky; top: 0; }}
  details {{ margin-bottom: 0.4rem; border: 1px solid #eee; border-radius: 4px; padding: 0.4rem 0.8rem; }}
  summary {{ cursor: pointer; font-weight: 600; }}
  .avisos {{ background: #fff8e1; border: 1px solid #ffe082; border-radius: 4px; padding: 0.8rem 1.2rem; }}
  .stats {{ display: flex; gap: 2rem; margin: 1rem 0; }}
  .stat-box {{ background: #f0f4ff; border-radius: 6px; padding: 0.6rem 1.2rem; }}
  .stat-box b {{ display: block; font-size: 1.4rem; }}
</style>
</head>
<body>
  <h1>Gold — fbref_fixtures</h1>
  <p class="subtitle">Mundial {EDICION_ANYO} — public.partido</p>

  <div class="stats">
    <div class="stat-box"><b>{total}</b>Partidos</div>
    <div class="stat-box"><b>{finalizados}</b>Finalizados</div>
  </div>

  <h2>Validaciones</h2>
  <div class="avisos"><ul>{avisos_html}</ul></div>

  <h2>Fase de grupos</h2>
  {grupos_html}

  <h2>Calendario completo</h2>
  <table>
    <thead>
      <tr>
        <th>Fecha</th><th>Fase</th><th>Grupo</th><th>Local</th><th>Marcador</th>
        <th>Visitante</th><th>Estadio</th><th>Estado</th>
      </tr>
    </thead>
    <tbody>{calendario_rows}</tbody>
  </table>
</body>
</html>
"""


def run() -> Path:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            calendario = _calendario(cur)
            avisos = _validaciones(cur)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(_build_html(calendario, avisos), encoding="utf-8")
    print(f"Reporte generado: {OUT_FILE}")
    return OUT_FILE


if __name__ == "__main__":
    run()
