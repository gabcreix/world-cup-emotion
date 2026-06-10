"""
Orquestador del pipeline fbref_fixtures.

Ejecuta las capas en orden:
    python -m world_cup.pipelines.fbref_fixtures.run

Flags:
    --bronze-only   Solo descarga el calendario y persiste en bronze (sin silver)
    --skip-db       Ejecuta todo pero no escribe en BD (útil para debug)
"""

import sys

from world_cup.pipelines.fbref_fixtures import bronze, silver


def main():
    bronze_only = "--bronze-only" in sys.argv
    skip_db     = "--skip-db"     in sys.argv

    print("=" * 60)
    print("BRONZE — Calendario de partidos desde FBref")
    print("=" * 60)
    _, run_id = bronze.run(skip_db=skip_db)

    if not bronze_only:
        print("\n" + "=" * 60)
        print("SILVER — Parseo y normalización")
        print("=" * 60)
        if run_id:
            silver.run(run_id=run_id, skip_db=skip_db)
        else:
            print("  [INFO] Sin run_id — omitiendo silver (usa --skip-db solo para depurar bronze)")


if __name__ == "__main__":
    main()
