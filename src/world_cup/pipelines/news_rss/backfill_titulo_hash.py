"""
Backfill puntual — noticia.titulo_hash.

Rellena titulo_hash para las noticias insertadas antes de la migración
024_noticia_titulo_hash.sql (titulo_hash IS NULL).

Si dos noticias antiguas tienen el mismo titulo_hash (títulos
equivalentes que no se detectaron en su momento), la primera se
actualiza y el resto se deja con titulo_hash NULL para no violar el
índice único.

Ejecutar:
    python -m world_cup.pipelines.news_rss.backfill_titulo_hash
"""

from world_cup import db
from world_cup.pipelines.news_rss.gold import _hash_titulo


def run() -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT noticia_id, titulo FROM noticia WHERE titulo_hash IS NULL ORDER BY noticia_id"
            )
            pendientes = cur.fetchall()

            actualizados = 0
            omitidos = 0
            for noticia_id, titulo in pendientes:
                titulo_hash = _hash_titulo(titulo)
                cur.execute(
                    """
                    UPDATE noticia SET titulo_hash = %s, actualizado_en = NOW()
                    WHERE noticia_id = %s
                      AND NOT EXISTS (
                          SELECT 1 FROM noticia o
                          WHERE o.titulo_hash = %s AND o.noticia_id != %s
                      )
                    """,
                    (titulo_hash, noticia_id, titulo_hash, noticia_id),
                )
                if cur.rowcount:
                    actualizados += 1
                else:
                    omitidos += 1

        conn.commit()

    print(f"  [BD] noticia.titulo_hash: {actualizados} actualizadas, {omitidos} omitidas (duplicado de titulo)")


if __name__ == "__main__":
    run()
