"""
Texto completo de noticias — Scraping del cuerpo del artículo.

Para cada `noticia` con `texto_completo IS NULL`, descarga la página y
extrae el cuerpo del artículo con `trafilatura` (extractor genérico,
funciona razonablemente bien en la mayoría de medios sin reglas por
fuente). Persiste el resultado en `noticia.texto_completo`.

Si la extracción falla o devuelve texto vacío, no se reintenta en
ejecuciones futuras (se marca con cadena vacía) para no golpear la misma
URL una y otra vez.

Uso:
    python -m world_cup.pipelines.news_rss.fulltext
"""

import trafilatura

from world_cup import db

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Carga de noticias pendientes
# ---------------------------------------------------------------------------

def _load_pendientes(cur) -> list[tuple[int, str]]:
    cur.execute(
        "SELECT noticia_id, url FROM noticia WHERE texto_completo IS NULL ORDER BY noticia_id"
    )
    return cur.fetchall()


# ---------------------------------------------------------------------------
# Extracción
# ---------------------------------------------------------------------------

def _extraer_texto(url: str) -> str | None:
    """Devuelve el texto del artículo, cadena vacía si no se pudo extraer
    nada útil, o None si la descarga falló."""
    descargado = trafilatura.fetch_url(url, user_agent=USER_AGENT)
    if descargado is None:
        return None
    texto = trafilatura.extract(descargado, include_comments=False, include_tables=False)
    return texto or ""


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def _persist(cur, noticia_id: int, texto: str) -> None:
    cur.execute(
        "UPDATE noticia SET texto_completo = %s, actualizado_en = NOW() WHERE noticia_id = %s",
        (texto, noticia_id),
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run() -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            pendientes = _load_pendientes(cur)
            print(f"  {len(pendientes)} noticias pendientes de texto completo")

            extraidas = 0
            fallidas = 0
            for noticia_id, url in pendientes:
                texto = _extraer_texto(url)
                if texto is None:
                    fallidas += 1
                    continue
                if texto:
                    extraidas += 1
                _persist(cur, noticia_id, texto)
                conn.commit()

            print(f"  [BD] texto_completo: {extraidas} extraídos, "
                  f"{fallidas} descargas fallidas (reintentables), "
                  f"{len(pendientes) - extraidas - fallidas} sin contenido extraíble")


if __name__ == "__main__":
    run()
