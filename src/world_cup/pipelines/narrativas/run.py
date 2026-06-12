"""
Orquestador del pipeline narrativas.

Ejecuta las analíticas del torneo actual, redacta una descripción breve con
gpt-4o-mini para cada dato destacado y hace upsert en `narrativa`.

Idempotente: no se inserta una narrativa si ya existe una con el mismo
`titulo` en las últimas 48h.

Uso:
    python -m world_cup.pipelines.narrativas.run
"""

import json

from openai import OpenAI

from world_cup import db
from world_cup.pipelines.narrativas import analiticas, clustering, historico

MODELO_LLM = "gpt-4o-mini"
SYSTEM_PROMPT = """
Eres un periodista deportivo especializado en fútbol internacional,
escribiendo para una audiencia hispanohablante global.
Tono: analítico pero accesible, con datos concretos, en español.
Evita clichés. Sé preciso y directo.
"""


def _generar_descripcion(client: OpenAI, contexto: dict) -> str:
    prompt = (
        "Redacta una narrativa breve (2-3 frases) en español sobre este dato "
        f"del Mundial 2026:\n{json.dumps(contexto, default=str, ensure_ascii=False)}\n\n"
        "Tono: analítico, con dato concreto. Sin clichés. Devuelve solo el texto."
    )
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content.strip()


def _existe_reciente(cur, titulo: str) -> bool:
    cur.execute(
        "SELECT 1 FROM narrativa WHERE titulo = %s AND creado_en > NOW() - INTERVAL '48 hours'",
        (titulo,),
    )
    return cur.fetchone() is not None


def _persist(cur, edicion_id: int, candidata: dict, descripcion: str) -> None:
    cur.execute(
        """
        INSERT INTO narrativa (
            edicion_id, titulo, tipo, descripcion, score_relevancia,
            entidades_json, fuente_datos
        ) VALUES (
            %(edicion_id)s, %(titulo)s, %(tipo)s, %(descripcion)s, %(score_relevancia)s,
            %(entidades_json)s, %(fuente_datos)s
        )
        """,
        {
            "edicion_id": edicion_id,
            "titulo": candidata["titulo"],
            "tipo": candidata["tipo"],
            "descripcion": descripcion,
            "score_relevancia": candidata["score_relevancia"],
            "entidades_json": json.dumps(candidata["entidades_json"]),
            "fuente_datos": candidata["fuente_datos"],
        },
    )


def run() -> None:
    client = OpenAI()

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            edicion_id = analiticas.load_edicion_id(cur)
            candidatas = (
                analiticas.generar(cur)
                + historico.generar(cur, edicion_id)
                + clustering.generar(cur, edicion_id, client)
            )

            if not candidatas:
                print("[INFO] No hay narrativas candidatas a partir de las analíticas.")
                return

            creadas = omitidas = 0
            for candidata in candidatas:
                if _existe_reciente(cur, candidata["titulo"]):
                    omitidas += 1
                    continue

                descripcion = _generar_descripcion(client, candidata["contexto"])
                _persist(cur, edicion_id, candidata, descripcion)
                creadas += 1
                print(f"  + {candidata['titulo']}")

        conn.commit()

    print(f"\n  [BD] narrativa: {creadas} creadas, {omitidas} ya existentes (últimas 48h)")


if __name__ == "__main__":
    run()
