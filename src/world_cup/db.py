import os
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv

load_dotenv()

_DATABASE_URL = os.environ["DATABASE_URL"]


@contextmanager
def get_conn():
    with psycopg.connect(_DATABASE_URL) as conn:
        yield conn


@contextmanager
def get_cursor():
    with get_conn() as conn:
        with conn.cursor() as cur:
            yield cur
            conn.commit()
