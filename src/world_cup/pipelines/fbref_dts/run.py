"""
Orquestador del pipeline fbref_dts.

Reutiliza el HTML de plantillas ya descargado por fbref_squads
(data/bronze/fbref_squads/squads/*.html).

Ejecuta las capas en orden:
    python -m world_cup.pipelines.fbref_dts.run

Flags:
    --bronze-only   Solo extrae candidatos a DT y persiste en bronze (sin silver/gold)
    --skip-db       Ejecuta todo pero no escribe en BD (silver/gold se omiten)
"""

import sys

from world_cup.pipelines.fbref_dts import bronze, gold, silver


def main():
    bronze_only = "--bronze-only" in sys.argv
    skip_db     = "--skip-db"     in sys.argv

    print("=" * 60)
    print("BRONZE — Candidatos a DT desde plantillas FBref (cache local)")
    print("=" * 60)
    _, run_id = bronze.run(skip_db=skip_db)

    if not bronze_only:
        print("\n" + "=" * 60)
        print("SILVER — Selección y normalización del DT por equipo")
        print("=" * 60)
        if run_id:
            silver.run(run_id=run_id, skip_db=skip_db)

            if not skip_db:
                print("\n" + "=" * 60)
                print("GOLD — Upsert en dt + enlace con participacion")
                print("=" * 60)
                gold.run(run_id=run_id)
        else:
            print("  [INFO] Sin run_id — omitiendo silver/gold (usa --skip-db solo para depurar bronze)")


if __name__ == "__main__":
    main()
