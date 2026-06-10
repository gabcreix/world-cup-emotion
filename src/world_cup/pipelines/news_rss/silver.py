"""
Silver layer — Ingesta de noticias vía RSS.

Lee bronze.news_rss_raw, normaliza y persiste en silver.news_item.
También produce data/silver/news_rss/items.json como copia local.
"""

import json
from pathlib import Path

from world_cup import db

ROOT = Path(__file__).resolve().parents[4]
SILVER_DIR = ROOT / "data" / "silver" / "news_rss"


# ---------------------------------------------------------------------------
# Normalización de un registro bronze → silver
# ---------------------------------------------------------------------------

def _normalize(bronze_id: int, run_id: str, raw: dict, fuente_id: int, idioma_fuente: str | None) -> dict:
    es_valido = True
    motivos: list[str] = []

    titulo = (raw.get("title") or "").strip()
    if not titulo:
        motivos.append("sin título")

    url = (raw.get("link") or "").strip()
    if not url:
        motivos.append("sin url")

    resumen = (raw.get("summary") or "").strip() or None

    fecha_publicacion = raw.get("published_parsed") or raw.get("updated_parsed") or None

    if motivos:
        es_valido = False

    return {
        "bronze_id":         bronze_id,
        "run_id":            run_id,
        "fuente_id":         fuente_id,
        "titulo":            titulo[:300],
        "url":               url[:500],
        "idioma":            idioma_fuente,
        "resumen":           resumen,
        "fecha_publicacion": fecha_publicacion,
        "es_valido":         es_valido,
        "motivo_invalido":   "; ".join(motivos) or None,
    }


# ---------------------------------------------------------------------------
# Persistencia en BD
# ---------------------------------------------------------------------------

def _persist_silver(records: list[dict]) -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for r in records:
                cur.execute(
                    """
                    INSERT INTO silver.news_item (
                        bronze_id, run_id,
                        fuente_id, titulo, url, idioma, resumen, fecha_publicacion,
                        es_valido, motivo_invalido
                    ) VALUES (
                        %(bronze_id)s, %(run_id)s,
                        %(fuente_id)s, %(titulo)s, %(url)s, %(idioma)s, %(resumen)s, %(fecha_publicacion)s,
                        %(es_valido)s, %(motivo_invalido)s
                    )
                    """,
                    r,
                )
        conn.commit()

    print(f"  [BD] {len(records)} registros en silver.news_item")


# ---------------------------------------------------------------------------
# Lectura desde bronze en BD
# ---------------------------------------------------------------------------

def _load_from_bronze(cur, run_id: str) -> list[tuple[int, int, dict]]:
    cur.execute(
        """
        SELECT id, fuente_id, raw_json
        FROM bronze.news_rss_raw
        WHERE run_id = %s
        ORDER BY id
        """,
        (run_id,),
    )
    return cur.fetchall()


def _load_idiomas(cur) -> dict[int, str | None]:
    cur.execute("SELECT fuente_id, idioma FROM fuente")
    return dict(cur.fetchall())


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run(run_id: str, skip_db: bool = False) -> list[dict]:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            bronze_rows = _load_from_bronze(cur, run_id)
            idioma_por_fuente = _load_idiomas(cur)

    if not bronze_rows:
        print("[ERROR] No hay datos en bronze.")
        return []

    records: list[dict] = []
    invalidos: list[str] = []

    for bronze_id, fuente_id, raw in bronze_rows:
        record = _normalize(bronze_id, run_id, raw, fuente_id, idioma_por_fuente.get(fuente_id))
        records.append(record)
        if not record["es_valido"]:
            invalidos.append(f"{raw.get('title')!r}: {record['motivo_invalido']}")

    print(f"  {len(records)} entradas normalizadas")
    if invalidos:
        print(f"\n  [WARN] {len(invalidos)} con incidencias:")
        for v in invalidos[:20]:
            print(f"    - {v}")

    if not skip_db:
        _persist_silver(records)

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    out = SILVER_DIR / "items.json"
    out.write_text(json.dumps(records, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nGuardado local: {out}")

    return records


if __name__ == "__main__":
    raise SystemExit("Usar a través de world_cup.pipelines.news_rss.run")
