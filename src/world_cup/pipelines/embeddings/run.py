"""
Embeddings — Vectoriza noticias para búsqueda semántica.

Recorre `noticia` buscando las que aún no tienen embedding (chunk_orden=1),
genera el vector con la API de OpenAI (text-embedding-3-small) a partir de
"titulo. resumen" y lo persiste en `embedding`.

Requiere OPENAI_API_KEY en el entorno (.env).

Uso:
    python -m world_cup.pipelines.embeddings.run
"""

from openai import OpenAI

from world_cup import db

MODELO = "text-embedding-3-small"
BATCH_SIZE = 100


# ---------------------------------------------------------------------------
# Carga de noticias pendientes
# ---------------------------------------------------------------------------

def _load_pendientes(cur) -> list[tuple[int, str, str | None]]:
    cur.execute(
        """
        SELECT n.noticia_id, n.titulo, n.resumen
        FROM noticia n
        LEFT JOIN embedding e
            ON e.noticia_id = n.noticia_id AND e.chunk_orden = 1
        WHERE e.embedding_id IS NULL
        ORDER BY n.noticia_id
        """
    )
    return cur.fetchall()


def _build_texto(titulo: str, resumen: str | None) -> str:
    if resumen:
        return f"{titulo}. {resumen}"
    return titulo


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def _persist_batch(cur, items: list[tuple[int, str]], vectors: list[list[float]]) -> None:
    for (noticia_id, texto), vector in zip(items, vectors):
        cur.execute(
            """
            INSERT INTO embedding (noticia_id, chunk_texto, chunk_orden, vector, modelo)
            VALUES (%s, %s, 1, %s, %s)
            ON CONFLICT (noticia_id, chunk_orden) DO NOTHING
            """,
            (noticia_id, texto, str(vector), MODELO),
        )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run() -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            pendientes = _load_pendientes(cur)

    if not pendientes:
        print("[INFO] No hay noticias pendientes de embedding.")
        return

    print(f"  {len(pendientes)} noticias pendientes")

    client = OpenAI()
    creadas = 0

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(pendientes), BATCH_SIZE):
                batch = pendientes[i:i + BATCH_SIZE]
                items = [
                    (noticia_id, _build_texto(titulo, resumen))
                    for noticia_id, titulo, resumen in batch
                ]
                textos = [texto for _, texto in items]

                resp = client.embeddings.create(model=MODELO, input=textos)
                vectors = [d.embedding for d in resp.data]

                _persist_batch(cur, items, vectors)
                creadas += len(items)
                print(f"  [BD] {min(i + BATCH_SIZE, len(pendientes))}/{len(pendientes)} procesadas")
        conn.commit()

    print(f"\n  [BD] embedding: {creadas} creadas")


if __name__ == "__main__":
    run()
