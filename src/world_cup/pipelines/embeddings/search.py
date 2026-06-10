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
    # Forzar UTF-8 en stdout/stderr (evita UnicodeEncodeError en consolas
    # Windows con páginas de código distintas, p.ej. cp1252).
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    if len(sys.argv) < 2:
        raise SystemExit(
            "Uso: python -m world_cup.pipelines.embeddings.search \"<consulta>\" [top_n]"
        )

    args = sys.argv[1:]
    top_n = TOP_N
    if len(args) > 1 and args[-1].isdigit():
        top_n = int(args[-1])
        args = args[:-1]

    consulta = " ".join(args)
    print(f"Consulta: {consulta!r} (top_n={top_n})")
    print(f"Bytes: {consulta.encode('utf-8')!r}\n")

    resultados = search(consulta, top_n)
    print(f"{len(resultados)} resultados\n")

    for titulo, url, distancia in resultados:
        print(f"  [{distancia:.4f}] {titulo}")
        print(f"           {url}")
