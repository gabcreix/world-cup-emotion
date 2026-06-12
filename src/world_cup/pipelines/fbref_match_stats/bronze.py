"""
Bronze layer — FBref match reports.

Descarga el HTML del match report de cada partido finalizado que aún no
tiene un registro en bronze.fbref_match_report_raw, lo guarda en disco
(cache) y persiste el HTML crudo en dicha tabla.

Es independiente de gold: si gold necesita reprocesar un partido (p.ej.
se borró stats_equipo), reutiliza el HTML ya presente en bronze sin
volver a descargarlo.

Reutiliza el driver/caché de world_cup.pipelines.fbref_squads.bronze.
"""

from pathlib import Path

from world_cup import db
from world_cup.pipelines.fbref_squads.bronze import _create_driver, _get_or_cache

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[4]
BRONZE_DIR = ROOT / "data" / "bronze" / "fbref_match_stats"


# ---------------------------------------------------------------------------
# Partidos pendientes
# ---------------------------------------------------------------------------

def _load_pendientes(cur) -> list[tuple[int, str]]:
    cur.execute(
        """
        SELECT p.partido_id, p.match_report_url
        FROM partido p
        WHERE p.estado = 'finalizado'
          AND p.match_report_url IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM bronze.fbref_match_report_raw r WHERE r.partido_id = p.partido_id
          )
        ORDER BY p.partido_id
        """
    )
    return cur.fetchall()


# ---------------------------------------------------------------------------
# Persistencia en BD
# ---------------------------------------------------------------------------

def _persist(partido_id: int, match_report_url: str, html: str) -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bronze.fbref_match_report_raw
                    (partido_id, match_report_url, html_raw)
                VALUES (%s, %s, %s)
                """,
                (partido_id, match_report_url, html),
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run() -> list[int]:
    """Descarga y persiste los match reports pendientes. Devuelve los
    partido_id procesados."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            pendientes = _load_pendientes(cur)

    if not pendientes:
        print("[INFO] No hay partidos finalizados pendientes de stats.")
        return []

    print(f"  {len(pendientes)} partidos pendientes de match report")

    print("[INFO] Iniciando Chrome (undetected). Se abrirá una ventana...")
    driver = _create_driver()

    procesados: list[int] = []
    try:
        for partido_id, match_report_url in pendientes:
            cache_path = BRONZE_DIR / f"{partido_id}.html"
            html = _get_or_cache(driver, match_report_url, cache_path)

            if "Just a moment" in html or "challenge-platform" in html:
                print(f"  [WARN] partido {partido_id}: HTML inválido (Cloudflare), omitiendo")
                continue

            _persist(partido_id, match_report_url, html)
            procesados.append(partido_id)
            print(f"  [BD] partido {partido_id}: match report persistido")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return procesados


if __name__ == "__main__":
    run()
