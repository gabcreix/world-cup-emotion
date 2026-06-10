"""
Orquestador del pipeline news_rss.

Ejecuta las capas en orden:
    python -m world_cup.pipelines.news_rss.run

Flags:
    --bronze-only   Solo descarga los feeds y persiste en bronze (sin silver/gold)
    --skip-db       Ejecuta todo pero no escribe en BD (silver/gold se omiten)
"""

import sys

from world_cup.pipelines.news_rss import bronze, gold, silver


def main():
    bronze_only = "--bronze-only" in sys.argv
    skip_db     = "--skip-db"     in sys.argv

    print("=" * 60)
    print("BRONZE — Descarga de feeds RSS")
    print("=" * 60)
    _, run_id = bronze.run(skip_db=skip_db)

    if not bronze_only:
        print("\n" + "=" * 60)
        print("SILVER — Normalización de noticias")
        print("=" * 60)
        if run_id:
            silver.run(run_id=run_id, skip_db=skip_db)

            if not skip_db:
                print("\n" + "=" * 60)
                print("GOLD — Upsert en noticia")
                print("=" * 60)
                gold.run(run_id=run_id)
        else:
            print("  [INFO] Sin run_id — omitiendo silver/gold (usa --skip-db solo para depurar bronze)")


if __name__ == "__main__":
    main()
