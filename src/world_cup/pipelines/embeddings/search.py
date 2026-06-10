"""
Búsqueda semántica sobre noticia.embedding usando pgvector, con
re-ranking opcional vía LLM (gpt-4o-mini) para filtrar/ordenar por
relevancia real (los embeddings por sí solos diluyen mucho con
consultas cortas o cruzando idiomas es/en).

Uso:
    python -m world_cup.pipelines.embeddings.search "<consulta>" [top_n]
    python -m world_cup.pipelines.embeddings.search "<consulta>" [top_n] --rerank
"""

import json
import sys

from openai import OpenAI

from world_cup import db
from world_cup.pipelines.embeddings.run import MODELO

TOP_N = 5
CANDIDATOS_RERANK = 20
RERANK_MODEL = "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Búsqueda vectorial
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Re-ranking con LLM
# ---------------------------------------------------------------------------

def rerank(query: str, candidatos: list[tuple[str, str, float]]) -> list[tuple[str, str, float]]:
    """Filtra y reordena candidatos por relevancia real respecto a la consulta."""
    if not candidatos:
        return []

    items_texto = "\n".join(
        f"{i}. {titulo}" for i, (titulo, _url, _dist) in enumerate(candidatos)
    )
    prompt = (
        "Eres un asistente que filtra resultados de búsqueda de noticias deportivas "
        "(Mundial 2026). Te doy una consulta y una lista de titulares candidatos "
        "(en español o inglés).\n\n"
        f'Consulta: "{query}"\n\n'
        f"Titulares candidatos:\n{items_texto}\n\n"
        "Devuelve SOLO un JSON con la lista de índices (0-based) de los titulares "
        "que sean realmente relevantes para la consulta, ordenados de más a menos "
        "relevante. Si ninguno es relevante, devuelve una lista vacía. "
        'Formato exacto: {"indices": [..]}'
    )

    client = OpenAI()
    resp = client.chat.completions.create(
        model=RERANK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)
    indices = data.get("indices", [])

    return [candidatos[i] for i in indices if 0 <= i < len(candidatos)]


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Forzar UTF-8 en stdout/stderr (evita UnicodeEncodeError en consolas
    # Windows con páginas de código distintas, p.ej. cp1252).
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    if len(sys.argv) < 2:
        raise SystemExit(
            "Uso: python -m world_cup.pipelines.embeddings.search \"<consulta>\" [top_n] [--rerank]"
        )

    args = sys.argv[1:]

    usar_rerank = "--rerank" in args
    if usar_rerank:
        args.remove("--rerank")

    top_n = TOP_N
    if len(args) > 1 and args[-1].isdigit():
        top_n = int(args[-1])
        args = args[:-1]

    consulta = " ".join(args)
    print(f"Consulta: {consulta!r} (top_n={top_n}, rerank={usar_rerank})\n")

    if usar_rerank:
        candidatos = search(consulta, CANDIDATOS_RERANK)
        resultados = rerank(consulta, candidatos)[:top_n]
    else:
        resultados = search(consulta, top_n)

    print(f"{len(resultados)} resultados\n")

    for titulo, url, distancia in resultados:
        print(f"  [{distancia:.4f}] {titulo}")
        print(f"           {url}")
