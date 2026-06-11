"""
Orquestador del pipeline historico_mundiales.

Uso:
    python -m world_cup.pipelines.historico_mundiales.run
"""

from world_cup.pipelines.historico_mundiales import bronze, gold


def main():
    print("=" * 60)
    print("BRONZE — Histórico de mundiales (1930-2022)")
    print("=" * 60)
    bronze.run()

    print("\n" + "=" * 60)
    print("GOLD — Upsert en historico_edicion / historico_resultado")
    print("=" * 60)
    gold.run()


if __name__ == "__main__":
    main()
