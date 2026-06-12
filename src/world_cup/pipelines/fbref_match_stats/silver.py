"""
Silver layer — FBref match reports.

Parsea el HTML de bronze.fbref_match_report_raw y devuelve una estructura
normalizada (eventos, stats por equipo, stats por jugador) lista para que
gold.py resuelva FKs y haga upsert.

No persiste tablas silver propias: para datos por partido (volumen bajo,
un registro por partido) se pasa directamente de bronze a gold.
"""

import re

from bs4 import BeautifulSoup, Comment

SQUAD_HASH_RE = re.compile(r"/squads/([0-9a-f]{8})/")
PLAYER_ID_RE = re.compile(r"/players/([0-9a-f]{8})/")
MINUTE_RE = re.compile(r"(\d+)\s*(?:\+\s*(\d+))?\s*['’]")


# ---------------------------------------------------------------------------
# Helpers numéricos
# ---------------------------------------------------------------------------

def _num(value, cast=int):
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    try:
        if cast is int:
            return int(float(value))
        return cast(value)
    except ValueError:
        return None


def _sum_field(jugadores: list[dict], campo: str) -> int | None:
    vals = [j[campo] for j in jugadores if j.get(campo) is not None]
    return sum(vals) if vals else None


# ---------------------------------------------------------------------------
# Tablas (algunas vienen dentro de comentarios HTML en FBref)
# ---------------------------------------------------------------------------

def _all_tables(soup: BeautifulSoup) -> dict[str, "BeautifulSoup"]:
    tables: dict[str, BeautifulSoup] = {}
    for t in soup.find_all("table"):
        if t.get("id"):
            tables[t["id"]] = t
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        if "<table" not in comment:
            continue
        inner = BeautifulSoup(comment, "lxml")
        for t in inner.find_all("table"):
            if t.get("id") and t["id"] not in tables:
                tables[t["id"]] = t
    return tables


def _table_rows(table, mark_starters: bool = False) -> list[dict]:
    rows = []
    is_bench = False
    for tr in table.select("tbody tr"):
        classes = tr.get("class") or []
        if "thead" in classes:
            is_bench = True
            continue

        th = tr.find("th", {"data-stat": "player"})
        if th is None or not th.get_text(strip=True):
            continue

        row: dict = {"player": th.get_text(strip=True)}
        if mark_starters:
            row["titular"] = not is_bench

        link = th.find("a")
        if link and link.get("href"):
            m = PLAYER_ID_RE.search(link["href"])
            if m:
                row["fbref_player_id"] = m.group(1)

        for td in tr.find_all("td"):
            stat = td.get("data-stat")
            if stat:
                row[stat] = td.get_text(strip=True)

        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Equipos (orden scorebox = local, visitante)
# ---------------------------------------------------------------------------

def _scorebox_squad_hashes(soup: BeautifulSoup) -> list[str]:
    box = soup.find("div", class_="scorebox")
    if box is None:
        return []
    hashes: list[str] = []
    for a in box.find_all("a", href=SQUAD_HASH_RE):
        m = SQUAD_HASH_RE.search(a["href"])
        if m and m.group(1) not in hashes:
            hashes.append(m.group(1))
    return hashes[:2]


def _resolve_sides(hashes: list[str], hash_to_fifa: dict[str, str],
                    local_fifa: str, visit_fifa: str) -> dict[str, str]:
    """Devuelve {'a': 'local'|'visitante', 'b': ...} según el orden del
    scorebox (a = primer equipo, b = segundo)."""
    sides: dict[str, str] = {}
    for i, h in enumerate(hashes):
        side_key = "a" if i == 0 else "b"
        fifa = hash_to_fifa.get(h)
        if fifa == local_fifa:
            sides[side_key] = "local"
        elif fifa == visit_fifa:
            sides[side_key] = "visitante"

    sides.setdefault("a", "local")
    sides.setdefault("b", "visitante")
    return sides


# ---------------------------------------------------------------------------
# Stats por jugador
# ---------------------------------------------------------------------------

STAT_CATEGORIES = ("summary", "passing", "defense", "possession", "misc")

FIELD_MAP: dict[str, tuple[str, type]] = {
    "minutes":              ("minutos_jugados", int),
    "goals":                ("goles", int),
    "assists":              ("asistencias", int),
    "shots":                ("tiros", int),
    "shots_on_target":      ("tiros_a_puerta", int),
    "passes_completed":     ("pases_completados", int),
    "passes":               ("pases_intentados", int),
    "assisted_shots":       ("pases_clave", int),
    "take_ons_won":         ("regates_exitosos", int),
    "take_ons":             ("regates_intentados", int),
    "carries":              ("conducciones", int),
    "interceptions":        ("intercepciones", int),
    "clearances":           ("despejes", int),
    "tackles_won":          ("entradas_exitosas", int),
    "challenges":           ("duelos_totales", int),
    "challenge_tackles":    ("duelos_ganados", int),
    "aerials_won":          ("duelos_aereos_ganados", int),
    "ball_recoveries":      ("recuperaciones", int),
    "cards_yellow":         ("tarjetas_amarillas", int),
    "cards_red":            ("tarjetas_rojas", int),
}

GK_FIELD_MAP: dict[str, str] = {
    "gk_saves":         "paradas",
    "gk_goals_against": "goles_encajados",
    "gk_pens_saved":    "paradas_penalti",
}


def _player_rows_for_squad(tables: dict, squad_hash: str) -> list[dict]:
    merged: dict[str, dict] = {}
    order: list[str] = []
    for cat in STAT_CATEGORIES:
        table = tables.get(f"stats_{squad_hash}_{cat}")
        if table is None:
            continue
        for row in _table_rows(table, mark_starters=(cat == "summary")):
            pid = row.get("fbref_player_id")
            if pid is None:
                continue
            if pid not in merged:
                merged[pid] = {}
                order.append(pid)
            merged[pid].update(row)
    return [merged[pid] for pid in order]


def _normalize_player(row: dict) -> dict:
    out: dict = {
        "nombre": row.get("player"),
        "fbref_player_id": row.get("fbref_player_id"),
        "posicion_fbref": row.get("position") or None,
        "titular": bool(row.get("titular", False)),
        "presiones": None,
        "presiones_exitosas": None,
        "nota": None,
        "stats_extra_json": None,
    }
    for fbref_key, (campo, cast) in FIELD_MAP.items():
        out[campo] = _num(row.get(fbref_key), cast)

    miscontrols = _num(row.get("miscontrols"), int)
    dispossessed = _num(row.get("dispossessed"), int)
    if miscontrols is not None or dispossessed is not None:
        out["perdidas_balon"] = (miscontrols or 0) + (dispossessed or 0)
    else:
        out["perdidas_balon"] = None

    return out


def _merge_keeper(jugadores: list[dict], row: dict) -> None:
    pid = row.get("fbref_player_id")

    extra: dict = {}
    for fbref_key, campo in GK_FIELD_MAP.items():
        val = _num(row.get(fbref_key), int)
        if val is not None:
            extra[campo] = val

    for j in jugadores:
        if j.get("fbref_player_id") == pid:
            if extra:
                j["stats_extra_json"] = extra
            if j.get("minutos_jugados") is None:
                j["minutos_jugados"] = _num(row.get("minutes"), int)
            return

    # Portero que no apareció en la tabla "summary" (caso raro)
    jugadores.append({
        "nombre": row.get("player"),
        "fbref_player_id": pid,
        "posicion_fbref": "GK",
        "titular": True,
        "minutos_jugados": _num(row.get("minutes"), int),
        "stats_extra_json": extra or None,
        "presiones": None,
        "presiones_exitosas": None,
        "nota": None,
        "perdidas_balon": None,
    })


# ---------------------------------------------------------------------------
# Stats de equipo
# ---------------------------------------------------------------------------

TEAM_STATS_EXTRA_MAP: dict[str, str] = {
    "Fouls": "faltas_cometidas",
    "Corners": "corners",
    "Offsides": "fueras_de_juego",
    "Clearances": "despejes",
}


def _parse_team_stats_extra(soup: BeautifulSoup, sides: dict[str, str]) -> dict[str, dict]:
    result: dict[str, dict] = {"local": {}, "visitante": {}}
    div = soup.find(id="team_stats_extra")
    if div is None:
        return result

    for group in div.find_all("div", recursive=False):
        items = [c.get_text(strip=True) for c in group.find_all("div")]
        for i in range(0, len(items) - 3, 4):
            val_a, label_a, label_b, val_b = items[i:i + 4]
            if label_a != label_b:
                continue
            campo = TEAM_STATS_EXTRA_MAP.get(label_a)
            if not campo:
                continue
            result[sides.get("a", "local")][campo] = _num(val_a)
            result[sides.get("b", "visitante")][campo] = _num(val_b)

    return result


def _parse_possession(soup: BeautifulSoup, sides: dict[str, str]) -> dict[str, int | None]:
    result: dict[str, int | None] = {"local": None, "visitante": None}
    div = soup.find(id="team_stats")
    if div is None:
        return result

    table = div.find("table")
    if table is None:
        return result

    rows = table.find_all("tr")
    for i, tr in enumerate(rows):
        if "Possession" not in tr.get_text():
            continue
        if i + 1 >= len(rows):
            break
        pcts = []
        for td in rows[i + 1].find_all("td"):
            m = re.search(r"(\d+)\s*%", td.get_text())
            if m:
                pcts.append(int(m.group(1)))
        if len(pcts) == 2:
            result[sides.get("a", "local")] = pcts[0]
            result[sides.get("b", "visitante")] = pcts[1]
        break

    return result


# ---------------------------------------------------------------------------
# Eventos de partido
# ---------------------------------------------------------------------------

def _parse_events(soup: BeautifulSoup, sides: dict[str, str]) -> list[dict]:
    eventos = []
    wrap = soup.find(id="events_wrap")
    if wrap is None:
        return eventos

    for div in wrap.find_all("div", class_="event"):
        classes = div.get("class", [])
        if "a" in classes:
            equipo = sides.get("a", "local")
        elif "b" in classes:
            equipo = sides.get("b", "visitante")
        else:
            continue

        text = div.get_text(" ", strip=True)
        m = MINUTE_RE.search(text)
        minuto = int(m.group(1)) if m else None
        minuto_adicional = int(m.group(2)) if m and m.group(2) else None

        icon = div.find("div", class_=re.compile(r"\bevent_icon\b"))
        icon_classes = icon.get("class", []) if icon else []

        tipo = None
        if "goal" in icon_classes:
            text_lower = text.lower()
            if "own goal" in text_lower:
                tipo = "gol_propia"
            elif "penalty" in text_lower:
                tipo = "gol_penalti"
            else:
                tipo = "gol"
        elif "yellow_card" in icon_classes:
            tipo = "tarjeta_amarilla"
        elif "second_yellow_card" in icon_classes:
            tipo = "doble_amarilla"
        elif "red_card" in icon_classes:
            tipo = "tarjeta_roja"
        elif "substitute_in" in icon_classes:
            tipo = "sustitucion"

        if tipo is None:
            continue

        jugadores = []
        for a in div.find_all("a", href=PLAYER_ID_RE):
            m2 = PLAYER_ID_RE.search(a["href"])
            jugadores.append({"nombre": a.get_text(strip=True), "fbref_player_id": m2.group(1)})

        if not jugadores:
            continue

        eventos.append({
            "equipo": equipo,
            "tipo": tipo,
            "minuto": minuto,
            "minuto_adicional": minuto_adicional,
            "jugador": jugadores[0],
            "jugador_rel": jugadores[1] if len(jugadores) > 1 else None,
        })

    return eventos


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def parse_match_report(html: str, hash_to_fifa: dict[str, str],
                        local_fifa: str, visit_fifa: str) -> dict:
    """Devuelve {"eventos": [...], "equipos": {"local": {...}, "visitante": {...}}}."""
    soup = BeautifulSoup(html, "lxml")
    tables = _all_tables(soup)

    hashes = _scorebox_squad_hashes(soup)
    sides = _resolve_sides(hashes, hash_to_fifa, local_fifa, visit_fifa)

    eventos = _parse_events(soup, sides)
    extra = _parse_team_stats_extra(soup, sides)
    posesion = _parse_possession(soup, sides)

    equipos: dict[str, dict] = {
        "local": {"jugadores": [], "stats": {}},
        "visitante": {"jugadores": [], "stats": {}},
    }

    for i, squad_hash in enumerate(hashes):
        side_key = "a" if i == 0 else "b"
        equipo = sides.get(side_key, "local" if i == 0 else "visitante")

        jugadores = [_normalize_player(row) for row in _player_rows_for_squad(tables, squad_hash)]

        keeper_table = tables.get(f"keeper_stats_{squad_hash}")
        if keeper_table is not None:
            for row in _table_rows(keeper_table):
                _merge_keeper(jugadores, row)

        equipos[equipo]["jugadores"] = jugadores
        equipos[equipo]["stats"] = {
            "posesion": posesion.get(equipo),
            "tiros_totales": _sum_field(jugadores, "tiros"),
            "tiros_a_puerta": _sum_field(jugadores, "tiros_a_puerta"),
            "tiros_bloqueados": None,
            "pases_totales": _sum_field(jugadores, "pases_intentados"),
            "pases_completados": _sum_field(jugadores, "pases_completados"),
            "pases_clave": _sum_field(jugadores, "pases_clave"),
            "corners": extra.get(equipo, {}).get("corners"),
            "fueras_de_juego": extra.get(equipo, {}).get("fueras_de_juego"),
            "faltas_cometidas": extra.get(equipo, {}).get("faltas_cometidas"),
            "despejes": extra.get(equipo, {}).get("despejes") or _sum_field(jugadores, "despejes"),
        }

    return {"eventos": eventos, "equipos": equipos}
