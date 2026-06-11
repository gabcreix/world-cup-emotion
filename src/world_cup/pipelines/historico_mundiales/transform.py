"""
Transformaciones — Histórico de mundiales.

Mapeos y funciones puras para convertir las filas crudas de
tournaments.csv / matches.csv (dataset Fjelstul World Cup Database) al
formato de `historico_edicion` y `historico_resultado`.

No depende de la BD: las filas resultantes usan `codigo_fifa` para
identificar países, que `gold.py` resuelve a `pais_id`.
"""

# ---------------------------------------------------------------------------
# Selecciones: código de equipo del dataset -> pais.codigo_fifa
# ---------------------------------------------------------------------------

CODE_MAP: dict[str, str] = {
    "DZA": "ALG", "AGO": "AGO", "ARG": "ARG", "AUS": "AUS", "AUT": "AUT",
    "BEL": "BEL", "BOL": "BOL", "BIH": "BIH", "BRA": "BRA", "BGR": "BUL",
    "CMR": "CMR", "CAN": "CAN", "CHL": "CHI", "CHN": "CHN", "COL": "COL",
    "CRI": "CRC", "HRV": "CRO", "CUB": "CUB", "CZE": "CZE", "CSK": "TCH",
    "DNK": "DEN", "IDN": "IDN", "DDR": "GDR", "ECU": "ECU", "EGY": "EGY",
    "SLV": "SLV", "ENG": "ENG", "FRA": "FRA", "DEU": "GER", "GHA": "GHA",
    "GRC": "GRE", "HTI": "HAI", "HND": "HON", "HUN": "HUN", "ISL": "ISL",
    "IRN": "IRN", "IRQ": "IRQ", "ISR": "ISR", "ITA": "ITA", "CIV": "CIV",
    "JAM": "JAM", "JPN": "JPN", "KWT": "KUW", "MEX": "MEX", "MAR": "MAR",
    "NLD": "NED", "NZL": "NZL", "NGA": "NGA", "PRK": "PRK", "NIR": "NIR",
    "NOR": "NOR", "PAN": "PAN", "PRY": "PAR", "PER": "PER", "POL": "POL",
    "PRT": "POR", "QAT": "QAT", "IRL": "IRL", "ROU": "ROU", "RUS": "RUS",
    "SAU": "KSA", "SCO": "SCO", "SEN": "SEN", "SRB": "SRB", "SCG": "SCG",
    "SVK": "SVK", "SVN": "SVN", "ZAF": "RSA", "KOR": "KOR", "SUN": "URS",
    "ESP": "ESP", "SWE": "SWE", "CHE": "SUI", "TGO": "TOG", "TTO": "TRI",
    "TUN": "TUN", "TUR": "TUR", "UKR": "UKR", "ARE": "UAE", "USA": "USA",
    "URY": "URU", "WAL": "WAL", "YUG": "YUG", "COD": "COD",
}

# tournaments.csv "winner" es el nombre completo del país (no el código)
WINNER_NAME_MAP: dict[str, str] = {
    "Uruguay": "URU",
    "Italy": "ITA",
    "West Germany": "GER",
    "Germany": "GER",
    "Brazil": "BRA",
    "England": "ENG",
    "Argentina": "ARG",
    "France": "FRA",
    "Spain": "ESP",
}

# matches.csv "stage_name" -> codigo de fase
FASE_MAP: dict[str, str] = {
    "group stage": "GRP",
    "second group stage": "GRP2",
    "round of 16": "R16",
    "quarter-finals": "QF",
    "semi-finals": "SF",
    "third-place match": "TP",
    "final": "F",
    "final round": "FR",
}


# ---------------------------------------------------------------------------
# Resultados
# ---------------------------------------------------------------------------

def build_resultado(raw: dict) -> dict | None:
    """Convierte una fila cruda de matches.csv en un dict listo para
    historico_resultado (con codigo_fifa en vez de pais_id). Devuelve None
    si la fase o algún equipo no tienen mapeo."""
    fase = FASE_MAP.get(raw["stage_name"])
    home = CODE_MAP.get(raw["home_team_code"])
    away = CODE_MAP.get(raw["away_team_code"])
    if fase is None or home is None or away is None:
        return None

    penaltis_local = penaltis_visitante = None
    if raw["penalty_shootout"] == "1":
        penaltis_local = int(raw["home_team_score_penalties"])
        penaltis_visitante = int(raw["away_team_score_penalties"])

    return {
        "tournament_id": raw["tournament_id"],
        "match_id": raw["match_id"],
        "fase": fase,
        "home_codigo_fifa": home,
        "away_codigo_fifa": away,
        "goles_local": int(raw["home_team_score"]),
        "goles_visitante": int(raw["away_team_score"]),
        "goles_local_prorroga": None,
        "goles_visit_prorroga": None,
        "penaltis_local": penaltis_local,
        "penaltis_visitante": penaltis_visitante,
        "fecha": raw["match_date"] or None,
    }


# ---------------------------------------------------------------------------
# Ediciones
# ---------------------------------------------------------------------------

def build_edicion(raw: dict, resultados: list[dict]) -> dict:
    """Convierte una fila cruda de tournaments.csv + sus resultados ya
    transformados en un dict listo para historico_edicion."""
    de_la_edicion = [r for r in resultados if r["tournament_id"] == raw["tournament_id"]]

    final = next((r for r in de_la_edicion if r["fase"] == "F"), None)
    tercer_puesto = next((r for r in de_la_edicion if r["fase"] == "TP"), None)

    campeon = WINNER_NAME_MAP.get(raw["winner"])
    subcampeon = None
    if final:
        subcampeon = _perdedor(final)

    tercero = cuarto = None
    if tercer_puesto:
        tercero = _ganador(tercer_puesto)
        cuarto = _perdedor(tercer_puesto)

    goles_totales = sum(r["goles_local"] + r["goles_visitante"] for r in de_la_edicion)
    partidos_totales = len(de_la_edicion)
    promedio_goles = round(goles_totales / partidos_totales, 2) if partidos_totales else None

    return {
        "tournament_id": raw["tournament_id"],
        "anyo": int(raw["year"]),
        "sede": raw["host_country"],
        "num_equipos": int(raw["count_teams"]) if raw["count_teams"] else None,
        "campeon_codigo_fifa": campeon,
        "subcampeon_codigo_fifa": subcampeon,
        "tercero_codigo_fifa": tercero,
        "cuarto_codigo_fifa": cuarto,
        "goles_totales": goles_totales,
        "partidos_totales": partidos_totales,
        "promedio_goles": promedio_goles,
        "asistencia_total": None,
    }


def _ganador(resultado: dict) -> str:
    if resultado["penaltis_local"] is not None:
        if resultado["penaltis_local"] > resultado["penaltis_visitante"]:
            return resultado["home_codigo_fifa"]
        return resultado["away_codigo_fifa"]
    if resultado["goles_local"] >= resultado["goles_visitante"]:
        return resultado["home_codigo_fifa"]
    return resultado["away_codigo_fifa"]


def _perdedor(resultado: dict) -> str:
    ganador = _ganador(resultado)
    if ganador == resultado["home_codigo_fifa"]:
        return resultado["away_codigo_fifa"]
    return resultado["home_codigo_fifa"]
