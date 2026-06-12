"""
Scheduler — orquesta la ejecución periódica de los pipelines del proyecto.

Uso:
    python -m world_cup.scheduler

Cadencia:
    - Cada 2 horas: fixtures -> stats de partido -> cadena de noticias
      (news_rss -> fulltext -> embeddings -> menciones -> sentimiento)
    - Diario a las 15:00: informe diario por email

Logging:
    data/logs/scheduler_YYYY-MM-DD.log (uno por día, también a stdout)

Si un pipeline falla, se loggea el error y se continúa con el siguiente.
"""

import datetime
import logging
import time
import traceback
from pathlib import Path

import schedule

from world_cup.pipelines.embeddings import run as embeddings_run
from world_cup.pipelines.fbref_fixtures import run as fbref_fixtures_run
from world_cup.pipelines.fbref_match_stats import run as fbref_match_stats_run
from world_cup.pipelines.menciones import run as menciones_run
from world_cup.pipelines.news_rss import run as news_rss_run
from world_cup.reports import email_diario

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "data" / "logs"


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"scheduler_{datetime.date.today().isoformat()}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def _run_safe(nombre: str, func, *args, **kwargs) -> None:
    logging.info(f"--- Inicio: {nombre} ---")
    try:
        func(*args, **kwargs)
        logging.info(f"--- Fin: {nombre} ---")
    except Exception:
        logging.error(f"--- Error en {nombre} ---\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Tareas programadas
# ---------------------------------------------------------------------------

def run_ciclo_datos() -> None:
    """Fixtures -> stats de partido -> cadena de noticias. Cada 2h."""
    _run_safe("fbref_fixtures", fbref_fixtures_run.main)
    _run_safe("fbref_match_stats", fbref_match_stats_run.main)
    _run_safe("news_rss", news_rss_run.main)
    _run_safe("embeddings", embeddings_run.run)
    _run_safe("menciones", menciones_run.run)


def run_email_diario() -> None:
    """Informe diario por email. Diario a las 15:00."""
    _run_safe("email_diario", email_diario.run)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    _setup_logging()
    logging.info("Scheduler iniciado")

    schedule.every(2).hours.do(run_ciclo_datos)
    schedule.every().day.at("15:00").do(run_email_diario)

    # Primera ejecución inmediata del ciclo de datos al arrancar
    run_ciclo_datos()

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
