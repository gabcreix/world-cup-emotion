"""
Orquestador del pipeline fbref_squads.

Ejecuta las capas en orden:
    python -m world_cup.pipelines.fbref_squads.run [--bronze-only] [--silver-only]

Flags:
    --bronze-only  Solo descarga HTMLs (sin parsear)
    --silver-only  Solo parsea HTMLs ya descargados (sin descargar)
"""

import sys

from world_cup.pipelines.fbref_squads import bronze, silver


def main():
    bronze_only = "--bronze-only" in sys.argv
    silver_only = "--silver-only" in sys.argv

    if not silver_only:
        print("=" * 60)
        print("BRONZE — Descarga de HTMLs desde FBref")
        print("=" * 60)
        bronze.run()

    if not bronze_only:
        print("\n" + "=" * 60)
        print("SILVER — Parseo y normalización")
        print("=" * 60)
        silver.run()


if __name__ == "__main__":
    main()
