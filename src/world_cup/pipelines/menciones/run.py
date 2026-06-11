"""
Menciones — Detección de entidades (selecciones, DTs, jugadores) en noticias.

Para cada entidad_tipo soportado, recorre `noticia` (titulo + resumen)
buscando los alias de `alias_entidad` y persiste una fila por cada
(noticia, entidad) detectada en `mencion`.

Idempotente vía UNIQUE(noticia_id, entidad_tipo, entidad_id) + ON CONFLICT.

Uso:
    python -m world_cup.pipelines.menciones.run
"""

import re

from world_cup import db

ENTIDAD_TIPOS = ("seleccion", "dt", "jugador")
CONTEXTO_RADIO = 80  # caracteres antes/después del match para el contexto


# ---------------------------------------------------------------------------
# Carga de alias y noticias
# ---------------------------------------------------------------------------

def _load_aliases(cur, entidad_tipo: str) -> list[tuple[str, int]]:
    cur.execute(
        "SELECT alias, entidad_id FROM alias_entidad WHERE entidad_tipo = %s",
        (entidad_tipo,),
    )
    return cur.fetchall()


def _load_noticias(cur) -> list[tuple[int, str, str | None]]:
    cur.execute("SELECT noticia_id, titulo, resumen FROM noticia ORDER BY noticia_id")
    return cur.fetchall()


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _build_pattern(aliases: list[tuple[str, int]]) -> tuple[re.Pattern, dict[str, int]]:
    """Construye un regex con todos los alias (más largos primero) y un
    mapeo alias en minúsculas -> entidad_id."""
    alias_to_entidad = {alias.lower(): entidad_id for alias, entidad_id in aliases}
    ordenados = sorted(alias_to_entidad, key=len, reverse=True)
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(a) for a in ordenados) + r")\b",
        re.IGNORECASE,
    )
    return pattern, alias_to_entidad


def _find_mentions(pattern: re.Pattern, alias_to_entidad: dict[str, int], texto: str) -> dict[int, str]:
    """Devuelve {entidad_id: contexto} para la primera mención de cada entidad en el texto."""
    encontrados: dict[int, str] = {}
    for m in pattern.finditer(texto):
        entidad_id = alias_to_entidad[m.group(0).lower()]
        if entidad_id in encontrados:
            continue
        inicio = max(0, m.start() - CONTEXTO_RADIO)
        fin = min(len(texto), m.end() + CONTEXTO_RADIO)
        encontrados[entidad_id] = texto[inicio:fin].strip()
    return encontrados


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def _persist_records(entidad_tipo: str, records: list[tuple[int, int, str]]) -> int:
    creadas = 0
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for noticia_id, entidad_id, contexto in records:
                cur.execute(
                    """
                    INSERT INTO mencion (noticia_id, entidad_tipo, entidad_id, contexto)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (noticia_id, entidad_tipo, entidad_id) DO NOTHING
                    """,
                    (noticia_id, entidad_tipo, entidad_id, contexto[:500]),
                )
                creadas += cur.rowcount
        conn.commit()
    return creadas


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run() -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            noticias = _load_noticias(cur)

            for entidad_tipo in ENTIDAD_TIPOS:
                aliases = _load_aliases(cur, entidad_tipo)

                if not aliases:
                    print(f"[WARN] No hay alias de '{entidad_tipo}' en alias_entidad. Omitiendo.")
                    continue

                pattern, alias_to_entidad = _build_pattern(aliases)

                records: list[tuple[int, int, str]] = []
                for noticia_id, titulo, resumen in noticias:
                    texto = titulo + ("\n" + resumen if resumen else "")
                    for entidad_id, contexto in _find_mentions(pattern, alias_to_entidad, texto).items():
                        records.append((noticia_id, entidad_id, contexto))

                print(f"[{entidad_tipo}] {len(records)} menciones detectadas sobre {len(noticias)} noticias")

                creadas = _persist_records(entidad_tipo, records)
                print(f"  [BD] mencion: {creadas} creadas, {len(records) - creadas} ya existentes\n")


if __name__ == "__main__":
    run()
