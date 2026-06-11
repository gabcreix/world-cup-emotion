"""
Sentimiento — Clasifica el sentimiento de cada mención (positivo/negativo/neutro)
hacia la entidad mencionada, usando gpt-4o-mini sobre el campo `contexto`.

Procesa menciones con `sentimiento IS NULL` y `contexto IS NOT NULL`, en lotes,
y persiste el resultado en `mencion.sentimiento`.

Requiere OPENAI_API_KEY en el entorno (.env).

Uso:
    python -m world_cup.pipelines.menciones.sentimiento
"""

import json

from openai import OpenAI

from world_cup import db

MODELO = "gpt-4o-mini"
BATCH_SIZE = 20
SENTIMIENTOS_VALIDOS = {"positivo", "negativo", "neutro"}


# ---------------------------------------------------------------------------
# Carga de menciones pendientes
# ---------------------------------------------------------------------------

def _load_pendientes(cur) -> list[tuple[int, str]]:
    cur.execute(
        """
        SELECT mencion_id, contexto FROM mencion
        WHERE sentimiento IS NULL AND contexto IS NOT NULL
        ORDER BY mencion_id
        """
    )
    return cur.fetchall()


# ---------------------------------------------------------------------------
# Clasificación con LLM
# ---------------------------------------------------------------------------

def _build_prompt(items: list[tuple[int, str]]) -> str:
    items_texto = "\n".join(f'{mencion_id}. "{contexto}"' for mencion_id, contexto in items)
    return (
        "Eres un asistente que analiza el sentimiento de fragmentos de noticias "
        "deportivas (Mundial 2026) hacia la entidad mencionada en cada fragmento "
        "(selección, jugador o entrenador).\n\n"
        f"Fragmentos:\n{items_texto}\n\n"
        "Para cada fragmento, clasifica el sentimiento hacia esa entidad como "
        '"positivo", "negativo" o "neutro" (informativo, sin carga emocional clara). '
        "Devuelve SOLO un JSON con este formato exacto: "
        '{"resultados": [{"id": <id>, "sentimiento": "<positivo|negativo|neutro>"}, ...]}'
    )


def _clasificar_lote(client: OpenAI, items: list[tuple[int, str]]) -> dict[int, str]:
    resp = client.chat.completions.create(
        model=MODELO,
        messages=[{"role": "user", "content": _build_prompt(items)}],
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)

    resultado = {}
    for item in data.get("resultados", []):
        sentimiento = item.get("sentimiento")
        if sentimiento in SENTIMIENTOS_VALIDOS:
            resultado[item["id"]] = sentimiento
    return resultado


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def _persist(cur, mencion_id: int, sentimiento: str) -> None:
    cur.execute(
        "UPDATE mencion SET sentimiento = %s, actualizado_en = NOW() WHERE mencion_id = %s",
        (sentimiento, mencion_id),
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run() -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            pendientes = _load_pendientes(cur)

    if not pendientes:
        print("[INFO] No hay menciones pendientes de sentimiento.")
        return

    print(f"  {len(pendientes)} menciones pendientes")

    client = OpenAI()
    clasificadas = sin_clasificar = 0

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(pendientes), BATCH_SIZE):
                batch = pendientes[i:i + BATCH_SIZE]
                resultado = _clasificar_lote(client, batch)

                for mencion_id, _contexto in batch:
                    sentimiento = resultado.get(mencion_id)
                    if sentimiento is None:
                        sin_clasificar += 1
                        continue
                    _persist(cur, mencion_id, sentimiento)
                    clasificadas += 1

                conn.commit()
                print(f"  [BD] {min(i + BATCH_SIZE, len(pendientes))}/{len(pendientes)} procesadas")

    print(f"\n  [BD] mencion.sentimiento: {clasificadas} clasificadas, {sin_clasificar} sin respuesta del modelo")


if __name__ == "__main__":
    run()
