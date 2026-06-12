"""
Orquestador del pipeline fbref_match_stats.

Ejecuta las capas en orden:
    python -m world_cup.pipelines.fbref_match_stats.run

Flags:
    --bronze-only   Solo descarga los match reports y los persiste en bronze
"""

import sys

from world_cup.pipelines.fbref_match_stats import bronze, gold


def main():
    bronze_only = "--bronze-only" in sys.argv

    print("=" * 60)
    print("BRONZE — Match reports de FBref")
    print("=" * 60)
    bronze.run()

    if not bronze_only:
        print("\n" + "=" * 60)
        print("GOLD — Eventos y stats de partido")
        print("=" * 60)
        gold.run()


if __name__ == "__main__":
    main()
