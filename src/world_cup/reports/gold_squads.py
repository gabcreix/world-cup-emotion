"""
Reporte HTML — Capa gold de fbref_squads.

Genera data/reports/gold_squads.html con:
    - Resumen por selección (jugadores convocados por posición)
    - Detalle de jugadores por selección
    - Validaciones (selecciones sin convocatoria, jugadores sin fecha, etc.)

Uso:
    python -m world_cup.reports.gold_squads
"""

import html
from pathlib import Path

from world_cup import db

EDICION_ANYO = 2026

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "data" / "reports"
OUT_FILE = OUT_DIR / "gold_squads.html"


def _resumen_por_seleccion(cur) -> list[dict]:
    cur.execute(
        """
        SELECT
            p.nombre AS pais,
            s.codigo_fifa,
            COUNT(c.convocatoria_id)                                            AS total,
            COUNT(*) FILTER (WHERE c.posicion_convocado = 'portero')           AS porteros,
            COUNT(*) FILTER (WHERE c.posicion_convocado = 'defensa')           AS defensas,
            COUNT(*) FILTER (WHERE c.posicion_convocado = 'centrocampista')    AS centrocampistas,
            COUNT(*) FILTER (WHERE c.posicion_convocado = 'delantero')         AS delanteros
        FROM seleccion s
        JOIN pais p           ON p.pais_id = s.pais_id
        JOIN participacion pa ON pa.seleccion_id = s.seleccion_id
        JOIN edicion e        ON e.edicion_id = pa.edicion_id AND e.anyo = %s
        LEFT JOIN convocatoria c ON c.participacion_id = pa.participacion_id
        GROUP BY p.nombre, s.codigo_fifa
        ORDER BY p.nombre
        """,
        (EDICION_ANYO,),
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _detalle_jugadores(cur) -> list[dict]:
    cur.execute(
        """
        SELECT
            p.nombre AS pais,
            s.codigo_fifa,
            j.nombre_completo,
            j.fecha_nacimiento,
            j.posicion,
            j.posicion_especifica,
            c.posicion_convocado
        FROM convocatoria c
        JOIN jugador j        ON j.jugador_id = c.jugador_id
        JOIN participacion pa ON pa.participacion_id = c.participacion_id
        JOIN seleccion s      ON s.seleccion_id = pa.seleccion_id
        JOIN pais p           ON p.pais_id = s.pais_id
        JOIN edicion e        ON e.edicion_id = pa.edicion_id AND e.anyo = %s
        ORDER BY p.nombre, j.nombre_completo
        """,
        (EDICION_ANYO,),
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _validaciones(cur) -> list[str]:
    avisos: list[str] = []

    cur.execute(
        """
        SELECT p.nombre
        FROM seleccion s
        JOIN pais p           ON p.pais_id = s.pais_id
        JOIN participacion pa ON pa.seleccion_id = s.seleccion_id
        JOIN edicion e        ON e.edicion_id = pa.edicion_id AND e.anyo = %s
        LEFT JOIN convocatoria c ON c.participacion_id = pa.participacion_id
        GROUP BY p.nombre, pa.participacion_id
        HAVING COUNT(c.convocatoria_id) = 0
        """,
        (EDICION_ANYO,),
    )
    sin_convocatoria = [r[0] for r in cur.fetchall()]
    if sin_convocatoria:
        avisos.append(f"Selecciones sin convocatoria: {', '.join(sin_convocatoria)}")

    cur.execute(
        """
        SELECT p.nombre, COUNT(*)
        FROM convocatoria c
        JOIN jugador j        ON j.jugador_id = c.jugador_id
        JOIN participacion pa ON pa.participacion_id = c.participacion_id
        JOIN seleccion s      ON s.seleccion_id = pa.seleccion_id
        JOIN pais p           ON p.pais_id = s.pais_id
        JOIN edicion e        ON e.edicion_id = pa.edicion_id AND e.anyo = %s
        WHERE j.fecha_nacimiento IS NULL
        GROUP BY p.nombre
        ORDER BY p.nombre
        """,
        (EDICION_ANYO,),
    )
    sin_fecha = cur.fetchall()
    if sin_fecha:
        detalle = ", ".join(f"{nombre} ({n})" for nombre, n in sin_fecha)
        avisos.append(f"Jugadores sin fecha de nacimiento: {detalle}")

    cur.execute(
        """
        SELECT j.nombre_completo, p.nombre, COUNT(*)
        FROM jugador j
        JOIN pais p ON p.pais_id = j.pais_id
        GROUP BY j.nombre_completo, p.nombre
        HAVING COUNT(*) > 1
        """
    )
    duplicados = cur.fetchall()
    if duplicados:
        detalle = ", ".join(f"{nombre} ({pais})" for nombre, pais, _ in duplicados)
        avisos.append(f"Posibles jugadores duplicados (mismo nombre + país): {detalle}")

    return avisos


def _build_html(resumen: list[dict], detalle: list[dict], avisos: list[str]) -> str:
    total_jugadores = sum(r["total"] for r in resumen)
    total_selecciones = len(resumen)

    avisos_html = (
        "".join(f"<li>{html.escape(a)}</li>" for a in avisos)
        if avisos
        else "<li>Sin incidencias detectadas.</li>"
    )

    resumen_rows = "".join(
        f"<tr>"
        f"<td>{html.escape(r['pais'])}</td>"
        f"<td>{r['codigo_fifa']}</td>"
        f"<td>{r['total']}</td>"
        f"<td>{r['porteros']}</td>"
        f"<td>{r['defensas']}</td>"
        f"<td>{r['centrocampistas']}</td>"
        f"<td>{r['delanteros']}</td>"
        f"</tr>"
        for r in resumen
    )

    # Agrupar detalle por país, en el mismo orden que el resumen
    detalle_por_pais: dict[str, list[dict]] = {}
    for j in detalle:
        detalle_por_pais.setdefault(j["pais"], []).append(j)

    detalle_html = ""
    for r in resumen:
        pais = r["pais"]
        jugadores = detalle_por_pais.get(pais, [])
        filas = "".join(
            f"<tr>"
            f"<td>{html.escape(j['nombre_completo'])}</td>"
            f"<td>{j['fecha_nacimiento'] or '—'}</td>"
            f"<td>{j['posicion']}</td>"
            f"<td>{j['posicion_especifica'] or '—'}</td>"
            f"</tr>"
            for j in jugadores
        )
        detalle_html += f"""
        <details>
          <summary>{html.escape(pais)} ({r['codigo_fifa']}) — {r['total']} jugadores</summary>
          <table>
            <thead>
              <tr><th>Jugador</th><th>Fecha nacimiento</th><th>Posición</th><th>Posición específica</th></tr>
            </thead>
            <tbody>{filas}</tbody>
          </table>
        </details>
        """

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Gold — fbref_squads ({EDICION_ANYO})</title>
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
  <h1>Gold — fbref_squads</h1>
  <p class="subtitle">Mundial {EDICION_ANYO} — public.jugador / public.convocatoria</p>

  <div class="stats">
    <div class="stat-box"><b>{total_selecciones}</b>Selecciones</div>
    <div class="stat-box"><b>{total_jugadores}</b>Jugadores convocados</div>
  </div>

  <h2>Validaciones</h2>
  <div class="avisos"><ul>{avisos_html}</ul></div>

  <h2>Resumen por selección</h2>
  <table>
    <thead>
      <tr>
        <th>Selección</th><th>FIFA</th><th>Total</th>
        <th>Porteros</th><th>Defensas</th><th>Centrocampistas</th><th>Delanteros</th>
      </tr>
    </thead>
    <tbody>{resumen_rows}</tbody>
  </table>

  <h2>Detalle por selección</h2>
  {detalle_html}
</body>
</html>
"""


def run() -> Path:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            resumen = _resumen_por_seleccion(cur)
            detalle = _detalle_jugadores(cur)
            avisos = _validaciones(cur)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(_build_html(resumen, detalle, avisos), encoding="utf-8")
    print(f"Reporte generado: {OUT_FILE}")
    return OUT_FILE


if __name__ == "__main__":
    run()
