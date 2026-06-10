"""
Orquestador del pipeline fbref_fixtures.

De momento solo capa bronze (descubrimiento + scraping del calendario):
    python -m world_cup.pipelines.fbref_fixtures.run

Flags:
    --skip-db       Ejecuta el scraping pero no escribe en BD (útil para debug)
"""

import sys

from world_cup.pipelines.fbref_fixtures import bronze


def main():
    skip_db = "--skip-db" in sys.argv

    print("=" * 60)
    print("BRONZE — Calendario de partidos desde FBref")
    print("=" * 60)
    bronze.run(skip_db=skip_db)


if __name__ == "__main__":
    main()
