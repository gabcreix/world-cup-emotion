"""
Bronze + silver — Fecha de nacimiento de los DTs.

Visita la página individual de cada DT en FBref (fbref_url, capturado en
silver.fbref_dt) y extrae su fecha de nacimiento, persistiendo el HTML
crudo en bronze.fbref_dt_profile_raw y actualizando
silver.fbref_dt.fecha_nacimiento.

Uso (tras haber corrido bronze + silver de fbref_dts):
    python -m world_cup.pipelines.fbref_dts.profiles <run_id>
"""

import json
import re
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup, Comment

from world_cup import db
from world_cup.pipelines.fbref_squads.bronze import _create_driver, _get_or_cache

ROOT = Path(__file__).resolve().parents[4]
BRONZE_DIR = ROOT / "data" / "bronze" / "fbref_dts" / "profiles"

BIRTH_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


# ---------------------------------------------------------------------------
# Parseo
# ---------------------------------------------------------------------------

def _find_meta_div(soup: BeautifulSoup):
    meta = soup.find("div", {"id": "meta"})
    if meta is not None:
        return meta

    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        if "id=\"meta\"" not in comment:
            continue
        inner = BeautifulSoup(comment, "lxml")
        meta = inner.find("div", {"id": "meta"})
        if meta is not None:
            return meta

    return None


def _extract_birth_date(html: str) -> dict:
    """
    Devuelve {"birth_date_iso": "YYYY-MM-DD"|None, "birth_date_text": str|None}.
    """
    soup = BeautifulSoup(html, "lxml")
    meta = _find_meta_div(soup)
    if meta is None:
        return {"birth_date_iso": None, "birth_date_text": None}

    span = meta.find(attrs={"itemprop": "birthDate"})
    if span is not None:
        data_birth = span.get("data-birth")
        text = span.get_text(" ", strip=True)
        iso = None
        if data_birth and BIRTH_DATE_RE.match(data_birth):
            iso = data_birth
        return {"birth_date_iso": iso, "birth_date_text": text or None}

    return {"birth_date_iso": None, "birth_date_text": None}


# ---------------------------------------------------------------------------
# Lectura / persistencia
# ---------------------------------------------------------------------------

def _load_dts(cur, run_id: str) -> list[tuple[int, str, str]]:
    """Devuelve (id, nombre_completo, fbref_url) para DTs válidos con fbref_url."""
    cur.execute(
        """
        SELECT id, nombre_completo, fbref_url
        FROM silver.fbref_dt
        WHERE run_id = %s AND es_valido = true AND fbref_url IS NOT NULL
        ORDER BY id
        """,
        (run_id,),
    )
    return cur.fetchall()


def _persist_raw(cur, run_id: str, fbref_dt_id: int, fbref_url: str, raw: dict) -> None:
    cur.execute(
        """
        INSERT INTO bronze.fbref_dt_profile_raw (run_id, fbref_dt_id, fbref_url, raw_json)
        VALUES (%s, %s, %s, %s)
        """,
        (run_id, fbref_dt_id, fbref_url, json.dumps(raw)),
    )


def _update_silver(cur, fbref_dt_id: int, fecha_nacimiento: str | None) -> None:
    cur.execute(
        "UPDATE silver.fbref_dt SET fecha_nacimiento = %s WHERE id = %s",
        (fecha_nacimiento, fbref_dt_id),
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run(run_id: str) -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            dts = _load_dts(cur, run_id)

    if not dts:
        print("[ERROR] No hay DTs con fbref_url para este run_id.")
        return

    print(f"[INFO] Iniciando Chrome (undetected). Se abrirá una ventana...")
    driver = _create_driver()

    sin_fecha: list[str] = []
    try:
        for fbref_dt_id, nombre, fbref_url in dts:
            safe_name = re.sub(r"[^\w]", "_", nombre)
            cache_path = BRONZE_DIR / f"{safe_name}.html"

            html = _get_or_cache(driver, fbref_url, cache_path)
            time.sleep(2)

            raw = _extract_birth_date(html)

            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    _persist_raw(cur, run_id, fbref_dt_id, fbref_url, raw)
                    _update_silver(cur, fbref_dt_id, raw["birth_date_iso"])
                conn.commit()

            if raw["birth_date_iso"]:
                print(f"  [OK] {nombre}: {raw['birth_date_iso']}")
            else:
                print(f"  [??] {nombre}: sin fecha ({raw['birth_date_text']!r})")
                sin_fecha.append(nombre)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    if sin_fecha:
        print(f"\n  [WARN] Sin fecha de nacimiento ({len(sin_fecha)}):")
        for n in sin_fecha:
            print(f"    - {n}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Uso: python -m world_cup.pipelines.fbref_dts.profiles <run_id>")
    run(sys.argv[1])
