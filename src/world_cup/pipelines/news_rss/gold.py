"""
Gold layer — Ingesta de noticias vía RSS.

Lee silver.news_item (es_valido = true) y hace upsert en public.noticia.
Idempotente: si la url ya existe, no se duplica.
"""

from world_cup import db


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
                cur.execute(
                    """
                    INSERT INTO noticia (
                        fuente_id, titulo, url, idioma, resumen, fecha_publicacion
                    ) VALUES (
                        %(fuente_id)s, %(titulo)s, %(url)s, %(idioma)s, %(resumen)s, %(fecha_publicacion)s
                    )
                    ON CONFLICT (url) DO NOTHING
                    """,
                    it,
                )
                creados += cur.rowcount

        conn.commit()

    print(f"  [BD] noticia: {creados} creadas, {len(items) - creados} ya existentes")


if __name__ == "__main__":
    raise SystemExit("Usar a través de world_cup.pipelines.news_rss.run")
