"""
Reporte HTML — Noticias (news_rss + menciones + embeddings).

Genera data/reports/news.html con:
    - Resumen por fuente (noticias, cobertura de embeddings)
    - Menciones detectadas por entidad (selecciones, DTs y jugadores)
    - Detalle de noticias recientes con sus menciones
    - Validaciones (noticias sin embedding, sin menciones, etc.)

Uso:
    python -m world_cup.reports.news
"""

import html
from pathlib import Path

from world_cup import db

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "data" / "reports"
OUT_FILE = OUT_DIR / "news.html"

NOTICIAS_RECIENTES = 50


def _resumen_por_fuente(cur) -> list[dict]:
    cur.execute(
        """
        SELECT
            f.nombre                                       AS fuente,
            COUNT(n.noticia_id)                            AS total,
            COUNT(e.embedding_id)                          AS con_embedding
        FROM fuente f
        LEFT JOIN noticia n ON n.fuente_id = f.fuente_id
        LEFT JOIN embedding e ON e.noticia_id = n.noticia_id AND e.chunk_orden = 1
        GROUP BY f.nombre
        ORDER BY total DESC, f.nombre
        """
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _menciones_por_seleccion(cur) -> list[dict]:
    cur.execute(
        """
        SELECT p.nombre AS nombre, COUNT(*) AS total
        FROM mencion m
        JOIN seleccion s ON s.seleccion_id = m.entidad_id
        JOIN pais p ON p.pais_id = s.pais_id
        WHERE m.entidad_tipo = 'seleccion'
        GROUP BY p.nombre
        ORDER BY total DESC, nombre
        """
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _menciones_por_dt(cur) -> list[dict]:
    cur.execute(
        """
        SELECT d.nombre_completo AS nombre, COUNT(*) AS total
        FROM mencion m
        JOIN dt d ON d.dt_id = m.entidad_id
        WHERE m.entidad_tipo = 'dt'
        GROUP BY d.nombre_completo
        ORDER BY total DESC, nombre
        """
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _menciones_por_jugador(cur, top_n: int = 20) -> list[dict]:
    cur.execute(
        """
        SELECT j.nombre_completo AS nombre, COUNT(*) AS total
        FROM mencion m
        JOIN jugador j ON j.jugador_id = m.entidad_id
        WHERE m.entidad_tipo = 'jugador'
        GROUP BY j.nombre_completo
        ORDER BY total DESC, nombre
        LIMIT %s
        """,
        (top_n,),
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _sentimiento_resumen(cur) -> dict[str, int]:
    cur.execute(
        "SELECT sentimiento, COUNT(*) FROM mencion WHERE sentimiento IS NOT NULL GROUP BY sentimiento"
    )
    return dict(cur.fetchall())


def _sentimiento_por_seleccion(cur) -> list[dict]:
    cur.execute(
        """
        SELECT
            p.nombre AS nombre,
            COUNT(*) FILTER (WHERE m.sentimiento = 'positivo') AS positivo,
            COUNT(*) FILTER (WHERE m.sentimiento = 'neutro')   AS neutro,
            COUNT(*) FILTER (WHERE m.sentimiento = 'negativo') AS negativo
        FROM mencion m
        JOIN seleccion s ON s.seleccion_id = m.entidad_id
        JOIN pais p ON p.pais_id = s.pais_id
        WHERE m.entidad_tipo = 'seleccion'
        GROUP BY p.nombre
        ORDER BY (positivo + neutro + negativo) DESC, nombre
        """
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _noticias_recientes(cur) -> list[dict]:
    cur.execute(
        """
        SELECT
            n.noticia_id,
            n.titulo,
            n.url,
            f.nombre AS fuente,
            n.fecha_publicacion,
            (e.embedding_id IS NOT NULL) AS tiene_embedding,
            COALESCE(
                array_agg(DISTINCT p.nombre) FILTER (WHERE m.entidad_tipo = 'seleccion'),
                '{}'
            ) AS selecciones,
            COALESCE(
                array_agg(DISTINCT d.nombre_completo) FILTER (WHERE m.entidad_tipo = 'dt'),
                '{}'
            ) AS dts,
            COALESCE(
                array_agg(DISTINCT j.nombre_completo) FILTER (WHERE m.entidad_tipo = 'jugador'),
                '{}'
            ) AS jugadores
        FROM noticia n
        JOIN fuente f ON f.fuente_id = n.fuente_id
        LEFT JOIN embedding e ON e.noticia_id = n.noticia_id AND e.chunk_orden = 1
        LEFT JOIN mencion m ON m.noticia_id = n.noticia_id
        LEFT JOIN seleccion s ON m.entidad_tipo = 'seleccion' AND s.seleccion_id = m.entidad_id
        LEFT JOIN pais p ON p.pais_id = s.pais_id
        LEFT JOIN dt d ON m.entidad_tipo = 'dt' AND d.dt_id = m.entidad_id
        LEFT JOIN jugador j ON m.entidad_tipo = 'jugador' AND j.jugador_id = m.entidad_id
        GROUP BY n.noticia_id, n.titulo, n.url, f.nombre, n.fecha_publicacion, e.embedding_id
        ORDER BY n.fecha_ingestion DESC
        LIMIT %s
        """,
        (NOTICIAS_RECIENTES,),
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _validaciones(cur) -> list[str]:
    avisos: list[str] = []

    cur.execute(
        """
        SELECT COUNT(*)
        FROM noticia n
        LEFT JOIN embedding e ON e.noticia_id = n.noticia_id AND e.chunk_orden = 1
        WHERE e.embedding_id IS NULL
        """
    )
    sin_embedding = cur.fetchone()[0]
    if sin_embedding:
        avisos.append(f"Noticias sin embedding: {sin_embedding}")

    cur.execute(
        """
        SELECT COUNT(*)
        FROM noticia n
        LEFT JOIN mencion m ON m.noticia_id = n.noticia_id
        WHERE m.mencion_id IS NULL
        """
    )
    sin_mencion = cur.fetchone()[0]
    if sin_mencion:
        avisos.append(f"Noticias sin ninguna mención detectada: {sin_mencion}")

    cur.execute("SELECT COUNT(*) FROM fuente WHERE activa")
    fuentes_activas = cur.fetchone()[0]
    cur.execute(
        """
        SELECT f.nombre
        FROM fuente f
        LEFT JOIN noticia n ON n.fuente_id = f.fuente_id
        WHERE f.activa
        GROUP BY f.fuente_id, f.nombre
        HAVING COUNT(n.noticia_id) = 0
        """
    )
    fuentes_sin_noticias = [r[0] for r in cur.fetchall()]
    if fuentes_sin_noticias:
        avisos.append(f"Fuentes activas sin noticias: {', '.join(fuentes_sin_noticias)}")

    return avisos


def _build_html(
    resumen_fuentes: list[dict],
    menciones_seleccion: list[dict],
    menciones_dt: list[dict],
    menciones_jugador: list[dict],
    sentimiento_resumen: dict[str, int],
    sentimiento_seleccion: list[dict],
    noticias: list[dict],
    avisos: list[str],
) -> str:
    total_noticias = sum(r["total"] for r in resumen_fuentes)
    total_con_embedding = sum(r["con_embedding"] for r in resumen_fuentes)

    avisos_html = (
        "".join(f"<li>{html.escape(a)}</li>" for a in avisos)
        if avisos
        else "<li>Sin incidencias detectadas.</li>"
    )

    fuentes_rows = "".join(
        f"<tr>"
        f"<td>{html.escape(r['fuente'])}</td>"
        f"<td>{r['total']}</td>"
        f"<td>{r['con_embedding']}</td>"
        f"</tr>"
        for r in resumen_fuentes
    )

    menciones_seleccion_rows = "".join(
        f"<tr><td>{html.escape(r['nombre'])}</td><td>{r['total']}</td></tr>"
        for r in menciones_seleccion
    )
    menciones_dt_rows = "".join(
        f"<tr><td>{html.escape(r['nombre'])}</td><td>{r['total']}</td></tr>"
        for r in menciones_dt
    )
    menciones_jugador_rows = "".join(
        f"<tr><td>{html.escape(r['nombre'])}</td><td>{r['total']}</td></tr>"
        for r in menciones_jugador
    )

    total_sentimiento = sum(sentimiento_resumen.values())
    positivo = sentimiento_resumen.get("positivo", 0)
    neutro = sentimiento_resumen.get("neutro", 0)
    negativo = sentimiento_resumen.get("negativo", 0)

    sentimiento_seleccion_rows = "".join(
        f"<tr><td>{html.escape(r['nombre'])}</td>"
        f"<td>😊 {r['positivo']}</td><td>😐 {r['neutro']}</td><td>😟 {r['negativo']}</td></tr>"
        for r in sentimiento_seleccion
    )

    noticias_rows = ""
    for n in noticias:
        selecciones = ", ".join(n["selecciones"]) if n["selecciones"] else "—"
        dts = ", ".join(n["dts"]) if n["dts"] else "—"
        jugadores = ", ".join(n["jugadores"]) if n["jugadores"] else "—"
        embedding_marca = "✅" if n["tiene_embedding"] else "—"
        fecha = n["fecha_publicacion"].strftime("%Y-%m-%d %H:%M") if n["fecha_publicacion"] else "—"
        noticias_rows += (
            f"<tr>"
            f"<td>{html.escape(n['fuente'])}</td>"
            f"<td>{fecha}</td>"
            f"<td><a href=\"{html.escape(n['url'])}\" target=\"_blank\">{html.escape(n['titulo'])}</a></td>"
            f"<td>{html.escape(selecciones)}</td>"
            f"<td>{html.escape(dts)}</td>"
            f"<td>{html.escape(jugadores)}</td>"
            f"<td>{embedding_marca}</td>"
            f"</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Noticias — Mundial 2026</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; }}
  h1 {{ margin-bottom: 0.2rem; }}
  .subtitle {{ color: #666; margin-top: 0; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 1rem; }}
  th, td {{ border: 1px solid #ddd; padding: 4px 8px; text-align: left; font-size: 0.9rem; }}
  th {{ background: #f4f4f4; position: sticky; top: 0; }}
  .avisos {{ background: #fff8e1; border: 1px solid #ffe082; border-radius: 4px; padding: 0.8rem 1.2rem; }}
  .stats {{ display: flex; gap: 2rem; margin: 1rem 0; flex-wrap: wrap; }}
  .stat-box {{ background: #f0f4ff; border-radius: 6px; padding: 0.6rem 1.2rem; }}
  .stat-box b {{ display: block; font-size: 1.4rem; }}
  .cols {{ display: flex; gap: 2rem; flex-wrap: wrap; }}
  .cols > div {{ flex: 1; min-width: 240px; }}
</style>
</head>
<body>
  <h1>Noticias — Mundial 2026</h1>
  <p class="subtitle">news_rss + menciones + embeddings</p>

  <div class="stats">
    <div class="stat-box"><b>{total_noticias}</b>Noticias</div>
    <div class="stat-box"><b>{total_con_embedding}</b>Con embedding</div>
    <div class="stat-box"><b>{sum(r['total'] for r in menciones_seleccion)}</b>Menciones de selecciones</div>
    <div class="stat-box"><b>{sum(r['total'] for r in menciones_dt)}</b>Menciones de DTs</div>
    <div class="stat-box"><b>{sum(r['total'] for r in menciones_jugador)}</b>Menciones de jugadores</div>
    <div class="stat-box"><b>{positivo} / {neutro} / {negativo}</b>Sentimiento (positivo / neutro / negativo) de {total_sentimiento} menciones</div>
  </div>

  <h2>Validaciones</h2>
  <div class="avisos"><ul>{avisos_html}</ul></div>

  <h2>Resumen por fuente</h2>
  <table>
    <thead><tr><th>Fuente</th><th>Noticias</th><th>Con embedding</th></tr></thead>
    <tbody>{fuentes_rows}</tbody>
  </table>

  <h2>Menciones por entidad</h2>
  <div class="cols">
    <div>
      <h3>Selecciones</h3>
      <table>
        <thead><tr><th>Selección</th><th>Menciones</th></tr></thead>
        <tbody>{menciones_seleccion_rows}</tbody>
      </table>
    </div>
    <div>
      <h3>Seleccionadores (DT)</h3>
      <table>
        <thead><tr><th>DT</th><th>Menciones</th></tr></thead>
        <tbody>{menciones_dt_rows}</tbody>
      </table>
    </div>
    <div>
      <h3>Jugadores (top {len(menciones_jugador)})</h3>
      <table>
        <thead><tr><th>Jugador</th><th>Menciones</th></tr></thead>
        <tbody>{menciones_jugador_rows}</tbody>
      </table>
    </div>
  </div>

  <h2>Sentimiento por selección</h2>
  <table>
    <thead><tr><th>Selección</th><th>Positivo</th><th>Neutro</th><th>Negativo</th></tr></thead>
    <tbody>{sentimiento_seleccion_rows}</tbody>
  </table>

  <h2>Noticias recientes (últimas {NOTICIAS_RECIENTES})</h2>
  <table>
    <thead>
      <tr>
        <th>Fuente</th><th>Fecha</th><th>Título</th>
        <th>Selecciones</th><th>DTs</th><th>Jugadores</th><th>Embedding</th>
      </tr>
    </thead>
    <tbody>{noticias_rows}</tbody>
  </table>
</body>
</html>
"""


def run() -> Path:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            resumen_fuentes = _resumen_por_fuente(cur)
            menciones_seleccion = _menciones_por_seleccion(cur)
            menciones_dt = _menciones_por_dt(cur)
            menciones_jugador = _menciones_por_jugador(cur)
            sentimiento_resumen = _sentimiento_resumen(cur)
            sentimiento_seleccion = _sentimiento_por_seleccion(cur)
            noticias = _noticias_recientes(cur)
            avisos = _validaciones(cur)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        _build_html(
            resumen_fuentes, menciones_seleccion, menciones_dt, menciones_jugador,
            sentimiento_resumen, sentimiento_seleccion, noticias, avisos,
        ),
        encoding="utf-8",
    )
    print(f"Reporte generado: {OUT_FILE}")
    return OUT_FILE


if __name__ == "__main__":
    run()
