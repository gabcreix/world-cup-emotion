"""
Bronze layer — FBref fixtures (calendario / resultados Mundial 2026).

Descarga el HTML del calendario de FBref, lo guarda en disco (cache) y
persiste las filas crudas en bronze.fbref_fixture_raw.

Reutiliza el driver/caché de world_cup.pipelines.fbref_squads.bronze.
"""

import json
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup, Comment

from world_cup import db
from world_cup.pipelines.fbref_squads.bronze import (
    BASE_URL,
    REQUEST_DELAY,
    TOURNAMENT_URL,
    _create_driver,
    _fetch_html,
    _get_or_cache,
)

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[4]
BRONZE_DIR = ROOT / "data" / "bronze" / "fbref_fixtures"

# URL conocida del calendario del Mundial 2026 (fallback si la discovery falla)
SCHEDULE_URL = "https://fbref.com/en/comps/1/schedule/World-Cup-Scores-and-Fixtures"


# ---------------------------------------------------------------------------
# Discovery: enlace "Scores & Fixtures" desde la página del torneo
# ---------------------------------------------------------------------------

def discover_schedule_url(driver) -> str | None:
    cache_path = BRONZE_DIR / "tournament_page.html"
    html = _get_or_cache(driver, TOURNAMENT_URL, cache_path)
    soup = BeautifulSoup(html, "lxml")

    for a in soup.select("a[href*='/schedule/']"):
        href = a["href"]
        if re.match(r"^/en/comps/\d+/.*schedule.*", href):
            return BASE_URL + href

    return SCHEDULE_URL


def fetch_schedule_html(driver, schedule_url: str) -> str:
    """Descarga siempre el calendario en vivo (no se cachea de forma
    permanente): cambia continuamente con resultados y enlaces a match
    reports a medida que avanza el torneo."""
    cache_path = BRONZE_DIR / "schedule.html"
    time.sleep(REQUEST_DELAY)
    html = _fetch_html(driver, schedule_url)

    if "Just a moment" in html or "challenge-platform" in html:
        print("  [WARN] Cloudflare al descargar el calendario")
        if cache_path.exists():
            print(f"  [cache] {cache_path.name} (fallback)")
            return cache_path.read_text(encoding="utf-8", errors="ignore")
        return html

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(html, encoding="utf-8")
    return html


# ---------------------------------------------------------------------------
# Parseo mínimo para bronze (sin normalizar)
# ---------------------------------------------------------------------------

def _extract_raw_fixtures(html: str) -> list[dict]:
    """
    Extrae filas de la tabla de calendario como dicts crudos.
    Cada celda con atributo data-stat se vuelca tal cual (texto + URL si
    contiene un enlace), sin normalización.
    """
    soup = BeautifulSoup(html, "lxml")

    table = None
    for t in soup.find_all("table"):
        if t.get("id", "").startswith("sched_"):
            table = t
            break
    if table is None:
        for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
            if "sched_" not in comment:
                continue
            inner = BeautifulSoup(comment, "lxml")
            for t in inner.find_all("table"):
                if t.get("id", "").startswith("sched_"):
                    table = t
                    break
            if table:
                break

    if table is None:
        return []

    rows = []
    for tr in table.select("tbody tr"):
        if "thead" in (tr.get("class") or []):
            continue

        row: dict = {}
        for cell in tr.find_all(["th", "td"]):
            stat = cell.get("data-stat")
            if not stat:
                continue
            row[stat] = cell.get_text(strip=True)
            link = cell.find("a")
            if link and link.get("href"):
                row[f"{stat}_url"] = BASE_URL + link["href"]

        if row.get("home_team") or row.get("away_team"):
            rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Persistencia en BD
# ---------------------------------------------------------------------------

def _persist_run(fixtures: list[dict]) -> str:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bronze.fbref_fixtures_run (num_partidos)
                VALUES (%s)
                RETURNING run_id
                """,
                (len(fixtures),),
            )
            run_id = str(cur.fetchone()[0])

            for raw in fixtures:
                cur.execute(
                    """
                    INSERT INTO bronze.fbref_fixture_raw (run_id, raw_json)
                    VALUES (%s, %s)
                    """,
                    (run_id, json.dumps(raw)),
                )
        conn.commit()

    print(f"\n  [BD] bronze — run_id: {run_id}")
    print(f"  [BD] {len(fixtures)} registros en bronze.fbref_fixture_raw")
    return run_id


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run(skip_db: bool = False) -> tuple[list[dict], str | None]:
    """
    Ejecuta la capa bronze completa.
    Devuelve (fixtures, run_id). run_id es None si skip_db=True.
    """
    print("[INFO] Iniciando Chrome (undetected). Se abrirá una ventana...")
    driver = _create_driver()

    try:
        print("=== BRONZE: Buscando calendario (Scores & Fixtures) ===")
        schedule_url = discover_schedule_url(driver)
        if not schedule_url:
            print("[ERROR] No se encontró el enlace del calendario.")
            return [], None

        print(f"  Calendario: {schedule_url}")
        html = fetch_schedule_html(driver, schedule_url)

        print("\n=== BRONZE: Extrayendo filas del calendario ===")
        fixtures = _extract_raw_fixtures(html)
        print(f"  {len(fixtures)} partidos encontrados")

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    run_id = None
    if not skip_db and fixtures:
        print("\n=== BRONZE: Persistiendo en BD ===")
        run_id = _persist_run(fixtures)

    return fixtures, run_id


if __name__ == "__main__":
    run()
