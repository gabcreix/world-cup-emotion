"""
Orquestador del pipeline fbref_squads.

Ejecuta las capas en orden:
    python -m world_cup.pipelines.fbref_squads.run

Flags:
    --bronze-only   Solo descarga HTMLs y persiste en bronze (sin silver)
    --silver-only   Solo normaliza desde disco local (sin Chrome, sin BD bronze)
    --skip-db       Ejecuta todo pero no escribe en BD (útil para debug)
"""

import sys

from world_cup.pipelines.fbref_squads import bronze, silver


def main():
    bronze_only = "--bronze-only" in sys.argv
    silver_only = "--silver-only" in sys.argv
    skip_db     = "--skip-db"     in sys.argv

    run_id = None

    if not silver_only:
        print("=" * 60)
        print("BRONZE — Descarga de HTMLs desde FBref")
        print("=" * 60)
        _, run_id = bronze.run(skip_db=skip_db)

    if not bronze_only:
        print("\n" + "=" * 60)
        print("SILVER — Parseo y normalización")
        print("=" * 60)
        # Si venimos de --silver-only no hay run_id → lee desde disco
        silver.run(run_id=run_id, skip_db=skip_db)


if __name__ == "__main__":
    main()
