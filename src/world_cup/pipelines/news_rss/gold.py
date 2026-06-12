"""
Gold layer — Ingesta de noticias vía RSS.

Lee silver.news_item (es_valido = true) y hace upsert en public.noticia.
Idempotente: si la url ya existe, no se duplica.

Deduplicación adicional por título normalizado (titulo_hash): distintas
fuentes pueden cubrir el mismo evento con URLs distintas pero títulos
equivalentes; en ese caso se descarta la segunda noticia.
"""

import hashlib
import re

from world_cup import db


def _normalizar_titulo(titulo: str) -> str:
    t = titulo.lower().strip()
    t = re.sub(r"[^a-záéíóúüñ0-9\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _hash_titulo(titulo: str) -> str:
    return hashlib.sha256(_normalizar_titulo(titulo).encode()).hexdigest()


def _load_silver_items(cur, run_id: str) -> list[dict]:
    cur.execute(
        """
        SELECT fuente_id, titulo, url, idioma, resumen, fecha_publicacion
        FROM silver.news_item
        WHERE run_id = %s AND es_valido = true
        """,
        (run_id,),
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def run(run_id: str) -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            items = _load_silver_items(cur, run_id)

            creados = 0
            for it in items:
                it["titulo_hash"] = _hash_titulo(it["titulo"])
                cur.execute(
                    """
                    INSERT INTO noticia (
                        fuente_id, titulo, url, idioma, resumen, fecha_publicacion, titulo_hash
                    ) VALUES (
                        %(fuente_id)s, %(titulo)s, %(url)s, %(idioma)s, %(resumen)s,
                        %(fecha_publicacion)s, %(titulo_hash)s
                    )
                    ON CONFLICT DO NOTHING
                    """,
                    it,
                )
                creados += cur.rowcount

        conn.commit()

    print(f"  [BD] noticia: {creados} creadas, {len(items) - creados} ya existentes")


if __name__ == "__main__":
    raise SystemExit("Usar a través de world_cup.pipelines.news_rss.run")
