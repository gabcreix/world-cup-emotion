import os
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv

load_dotenv()

_DATABASE_URL = os.environ["DATABASE_URL"]


@contextmanager
def get_conn():
    # prepare_threshold=None: el pooler de Supabase (pgbouncer, modo
    # transacción) no soporta prepared statements entre conexiones.
    with psycopg.connect(_DATABASE_URL, prepare_threshold=None) as conn:
        yield conn


@contextmanager
def get_cursor():
    with get_conn() as conn:
        with conn.cursor() as cur:
            yield cur
            conn.commit()
