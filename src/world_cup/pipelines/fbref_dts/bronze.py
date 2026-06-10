"""
Bronze layer — FBref DTs (entrenadores).

Reutiliza el HTML de las plantillas ya descargado por fbref_squads
(data/bronze/fbref_squads/squads/*.html) — no vuelve a scrapear.

Extrae de forma genérica los párrafos del bloque #meta de cada página
de plantilla, junto con los candidatos a "Manager"/"Head Coach"/"Coach",
para que la capa silver decida cuál es el entrenador.

Requiere haber ejecutado antes:
    python -m world_cup.pipelines.fbref_squads.run --bronze-only
(o el pipeline completo) para tener el HTML cacheado en disco.
"""

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup, Comment

from world_cup import db

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[4]
SQUADS_BRONZE_DIR = ROOT / "data" / "bronze" / "fbref_squads"
SQUADS_DIR = SQUADS_BRONZE_DIR / "squads"
TEAM_URLS_FILE = SQUADS_BRONZE_DIR / "team_urls.json"

MANAGER_LABELS = ("manager", "head coach", "coach")


# ---------------------------------------------------------------------------
# Parseo mínimo para bronze (sin normalizar)
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


def _extract_raw_meta(html: str) -> dict:
    """
    Extrae los párrafos del bloque #meta y los candidatos a entrenador.

    Devuelve:
        {
            "meta_paragraphs": [str, ...],
            "manager_candidates": [{"label": str, "value": str, "fbref_url": str|None}, ...]
        }
    """
    soup = BeautifulSoup(html, "lxml")
    meta = _find_meta_div(soup)

    meta_paragraphs: list[str] = []
    manager_candidates: list[dict] = []

    if meta is None:
        return {"meta_paragraphs": meta_paragraphs, "manager_candidates": manager_candidates}

    for p in meta.find_all("p"):
        text = p.get_text(" ", strip=True)
        if text:
            meta_paragraphs.append(text)

        strong = p.find("strong")
        if strong is None:
            continue

        label = strong.get_text(strip=True)
        if not any(label.lower().startswith(m) for m in MANAGER_LABELS):
            continue

        # Texto tras la etiqueta <strong>...</strong>:
        value_parts = []
        for sib in strong.next_siblings:
            if hasattr(sib, "get_text"):
                value_parts.append(sib.get_text(" ", strip=True))
            else:
                value_parts.append(str(sib))
        value = " ".join(v for v in value_parts if v).strip(" : ")

        link = p.find("a")
        fbref_url = ("https://fbref.com" + link["href"]) if link else None

        manager_candidates.append({"label": label, "value": value, "fbref_url": fbref_url})

    return {"meta_paragraphs": meta_paragraphs, "manager_candidates": manager_candidates}


# ---------------------------------------------------------------------------
# Persistencia en BD
# ---------------------------------------------------------------------------

def _persist_run(records: list[tuple[str, str, dict]]) -> str:
    num_equipos = len({r[0] for r in records})

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bronze.fbref_dts_run (num_equipos)
                VALUES (%s)
                RETURNING run_id
                """,
                (num_equipos,),
            )
            run_id = str(cur.fetchone()[0])

            for team_name, team_url, raw_json in records:
                cur.execute(
                    """
                    INSERT INTO bronze.fbref_dt_raw
                        (run_id, team_name_fbref, fbref_squad_url, raw_json)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (run_id, team_name, team_url, json.dumps(raw_json)),
                )
        conn.commit()

    print(f"\n  [BD] bronze — run_id: {run_id}")
    print(f"  [BD] {len(records)} registros en bronze.fbref_dt_raw ({num_equipos} equipos)")
    return run_id


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run(skip_db: bool = False) -> tuple[list[tuple[str, str, dict]], str | None]:
    """
    Lee el HTML de plantillas cacheado y extrae los candidatos a DT.
    Devuelve (records, run_id). run_id es None si skip_db=True.
    records: lista de (team_name_fbref, fbref_squad_url, raw_json)
    """
    if not SQUADS_DIR.exists():
        print(f"[ERROR] No existe {SQUADS_DIR}.")
        print("        Ejecuta antes: python -m world_cup.pipelines.fbref_squads.run --bronze-only")
        return [], None

    team_urls: dict[str, str] = {}
    if TEAM_URLS_FILE.exists():
        team_urls = json.loads(TEAM_URLS_FILE.read_text(encoding="utf-8"))

    records: list[tuple[str, str, dict]] = []
    sin_candidato: list[str] = []
    sin_html: list[str] = []

    for team_name, team_url in sorted(team_urls.items()):
        safe_name = re.sub(r"[^\w]", "_", team_name)
        html_file = SQUADS_DIR / f"{safe_name}.html"
        if not html_file.exists():
            sin_html.append(team_name)
            continue

        html = html_file.read_text(encoding="utf-8")
        raw = _extract_raw_meta(html)
        records.append((team_name, team_url, raw))

        if not raw["manager_candidates"]:
            sin_candidato.append(team_name)

    print(f"  {len(records)} equipos procesados")
    if sin_html:
        print(f"\n  [WARN] Sin HTML cacheado ({len(sin_html)}):")
        for t in sin_html[:20]:
            print(f"    - {t}")
    if sin_candidato:
        print(f"\n  [WARN] Sin candidato a DT ({len(sin_candidato)}):")
        for t in sin_candidato[:20]:
            print(f"    - {t}")

    run_id = None
    if not skip_db:
        run_id = _persist_run(records)

    return records, run_id


if __name__ == "__main__":
    run()
