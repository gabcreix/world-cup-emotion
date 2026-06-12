"""
Narrativas — Clustering de noticias por embeddings.

Agrupa noticias de las últimas 24h cuyos embeddings son muy similares
(distancia coseno < 0.15) para detectar temas emergentes de prensa que
todavía no están capturados por las analíticas estructuradas.

Misma interfaz que `analiticas.py` / `historico.py`: cada función devuelve
`None` o una lista de dicts con `titulo`, `tipo`, `fuente_datos`,
`score_relevancia`, `entidades_json` y `contexto`.
"""

import datetime

DISTANCIA_MAX = 0.15
MIN_NOTICIAS = 5

# Tipos de entidad de `mencion` cuyo nombre se puede resolver para el título.
_QUERIES_NOMBRE = {
    "seleccion": (
        "SELECT p.nombre FROM seleccion s JOIN pais p ON p.pais_id = s.pais_id "
        "WHERE s.seleccion_id = %s"
    ),
    "jugador": "SELECT nombre_completo FROM jugador WHERE jugador_id = %s",
    "dt": "SELECT nombre_completo FROM dt WHERE dt_id = %s",
    "arbitro": "SELECT nombre_completo FROM arbitro WHERE arbitro_id = %s",
    "estadio": "SELECT ciudad FROM estadio WHERE estadio_id = %s",
}


def _nombre_entidad(cur, entidad_tipo: str, entidad_id: int) -> str | None:
    query = _QUERIES_NOMBRE.get(entidad_tipo)
    if not query:
        return None
    cur.execute(query, (entidad_id,))
    row = cur.fetchone()
    return row[0] if row else None


def _entidad_principal(cur, noticia_ids: list[int]) -> tuple[str, int] | None:
    cur.execute(
        """
        SELECT entidad_tipo, entidad_id, COUNT(*) AS apariciones
        FROM mencion
        WHERE noticia_id = ANY(%s)
        GROUP BY entidad_tipo, entidad_id
        ORDER BY apariciones DESC
        LIMIT 1
        """,
        (noticia_ids,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return row[0], row[1]


def _find(parent: dict, x: int) -> int:
    while parent[x] != x:
        x = parent[x]
    return x


def _union(parent: dict, a: int, b: int) -> None:
    parent.setdefault(a, a)
    parent.setdefault(b, b)
    ra, rb = _find(parent, a), _find(parent, b)
    if ra != rb:
        parent[ra] = rb


def _clusters_recientes(cur) -> list[list[int]]:
    cur.execute(
        """
        SELECT e1.noticia_id, e2.noticia_id
        FROM embedding e1
        JOIN embedding e2 ON e1.noticia_id < e2.noticia_id
        JOIN noticia n1 ON n1.noticia_id = e1.noticia_id
        JOIN noticia n2 ON n2.noticia_id = e2.noticia_id
        WHERE n1.fecha_ingestion > NOW() - INTERVAL '24 hours'
          AND n2.fecha_ingestion > NOW() - INTERVAL '24 hours'
          AND (e1.vector <=> e2.vector) < %s
        """,
        (DISTANCIA_MAX,),
    )

    parent: dict[int, int] = {}
    for a, b in cur.fetchall():
        _union(parent, a, b)

    grupos: dict[int, list[int]] = {}
    for nodo in parent:
        raiz = _find(parent, nodo)
        grupos.setdefault(raiz, []).append(nodo)

    return [miembros for miembros in grupos.values() if len(miembros) >= MIN_NOTICIAS]


def temas_emergentes(cur, edicion_id: int) -> list[dict]:
    candidatas = []
    hoy = datetime.date.today().isoformat()

    for noticia_ids in _clusters_recientes(cur):
        n = len(noticia_ids)

        cur.execute(
            "SELECT titulo FROM noticia WHERE noticia_id = ANY(%s) ORDER BY fecha_ingestion DESC LIMIT 5",
            (noticia_ids,),
        )
        titulares = [row[0] for row in cur.fetchall()]

        principal = _entidad_principal(cur, noticia_ids)
        entidades_json = []
        nombre = None
        if principal:
            entidad_tipo, entidad_id = principal
            nombre = _nombre_entidad(cur, entidad_tipo, entidad_id)
            if nombre:
                entidades_json.append({"tipo": entidad_tipo, "id": entidad_id})

        if nombre:
            titulo = f"Tema emergente en la prensa: {n} noticias citan a {nombre} ({hoy})"
        else:
            titulo = f"Tema emergente en la prensa del Mundial 2026: {n} noticias relacionadas ({hoy})"

        candidatas.append({
            "titulo": titulo,
            "tipo": "curiosidad",
            "fuente_datos": "torneo_actual",
            "score_relevancia": min(1.0, 0.4 + 0.05 * (n - MIN_NOTICIAS)),
            "entidades_json": entidades_json,
            "contexto": {
                "tipo_narrativa": "tema_emergente_prensa",
                "fecha": hoy,
                "num_noticias": n,
                "entidad_principal": nombre,
                "titulares_muestra": titulares,
            },
        })

    return candidatas


GENERADORES = [temas_emergentes]


def generar(cur, edicion_id: int) -> list[dict]:
    """Ejecuta el clustering de embeddings y devuelve las narrativas candidatas (sin persistir)."""
    candidatas = []
    for generador in GENERADORES:
        candidatas.extend(generador(cur, edicion_id))
    return candidatas
