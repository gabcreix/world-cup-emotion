"""
Búsqueda semántica sobre noticia.embedding usando pgvector.

Uso:
    python -m world_cup.pipelines.embeddings.search "lesiones de jugadores antes del Mundial"
"""

import sys

from openai import OpenAI

from world_cup import db
from world_cup.pipelines.embeddings.run import MODELO

TOP_N = 5


def search(query: str, top_n: int = TOP_N) -> list[tuple[str, str, float]]:
    client = OpenAI()
    resp = client.embeddings.create(model=MODELO, input=[query])
    query_vector = resp.data[0].embedding

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT n.titulo, n.url, e.vector <=> %s AS distancia
                FROM embedding e
                JOIN noticia n ON n.noticia_id = e.noticia_id
                ORDER BY e.vector <=> %s
                LIMIT %s
                """,
                (str(query_vector), str(query_vector), top_n),
            )
            return cur.fetchall()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Uso: python -m world_cup.pipelines.embeddings.search \"<consulta>\"")

    consulta = " ".join(sys.argv[1:])
    print(f"Consulta: {consulta!r}\n")

    for titulo, url, distancia in search(consulta):
        print(f"  [{distancia:.4f}] {titulo}")
        print(f"           {url}")
