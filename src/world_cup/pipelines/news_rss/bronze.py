"""
Bronze layer — Ingesta de noticias vía RSS.

Lee las fuentes activas con rss_url en `fuente`, descarga cada feed con
feedparser y persiste las entradas crudas en bronze.news_rss_raw.

Uso:
    python -m world_cup.pipelines.news_rss.run
"""

import calendar
import datetime
import json
import time

import feedparser

from world_cup import db


# ---------------------------------------------------------------------------
# Fuentes activas
# ---------------------------------------------------------------------------

def _load_fuentes(cur) -> list[tuple[int, str, str, str | None]]:
    """Devuelve (fuente_id, codigo, rss_url, idioma) de fuentes activas con rss_url."""
    cur.execute(
        """
        SELECT fuente_id, codigo, rss_url, idioma
        FROM fuente
        WHERE activa = TRUE AND rss_url IS NOT NULL
        ORDER BY codigo
        """
    )
    return cur.fetchall()


# ---------------------------------------------------------------------------
# Descarga de feeds
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _fetch_feed_entries(rss_url: str) -> list[dict]:
    feed = feedparser.parse(rss_url, agent=USER_AGENT)

    if not feed.entries:
        print(f"    [DEBUG] status={feed.get('status')} bozo={feed.get('bozo')} "
              f"bozo_exception={feed.get('bozo_exception')!r}")

    entries = []
    for entry in feed.entries:
        item = dict(entry)
        for key in ("published_parsed", "updated_parsed"):
            struct = item.get(key)
            if isinstance(struct, time.struct_time):
                item[key] = (
                    datetime.datetime.fromtimestamp(
                        calendar.timegm(struct), tz=datetime.timezone.utc
                    ).isoformat()
                )
        entries.append(item)
    return entries


# ---------------------------------------------------------------------------
# Persistencia en BD
# ---------------------------------------------------------------------------

def _persist_run(records: list[tuple[int, dict]]) -> str:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bronze.news_rss_run (num_items)
                VALUES (%s)
                RETURNING run_id
                """,
                (len(records),),
            )
            run_id = str(cur.fetchone()[0])

            for fuente_id, raw_json in records:
                cur.execute(
                    """
                    INSERT INTO bronze.news_rss_raw (run_id, fuente_id, raw_json)
                    VALUES (%s, %s, %s)
                    """,
                    (run_id, fuente_id, json.dumps(raw_json, default=str)),
                )
        conn.commit()

    print(f"\n  [BD] bronze — run_id: {run_id}")
    print(f"  [BD] {len(records)} registros en bronze.news_rss_raw")
    return run_id


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run(skip_db: bool = False) -> tuple[list[tuple[int, dict]], str | None]:
    """
    Descarga los feeds de las fuentes activas.
    Devuelve (records, run_id). run_id es None si skip_db=True.
    records: lista de (fuente_id, raw_json).
    """
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            fuentes = _load_fuentes(cur)

    if not fuentes:
        print("[ERROR] No hay fuentes activas con rss_url.")
        return [], None

    records: list[tuple[int, dict]] = []
    for fuente_id, codigo, rss_url, _idioma in fuentes:
        entries = _fetch_feed_entries(rss_url)
        print(f"  {codigo}: {len(entries)} entradas ({rss_url})")
        for entry in entries:
            records.append((fuente_id, entry))

    print(f"\n  Total: {len(records)} entradas de {len(fuentes)} fuentes")

    run_id = None
    if not skip_db:
        run_id = _persist_run(records)

    return records, run_id


if __name__ == "__main__":
    run()
