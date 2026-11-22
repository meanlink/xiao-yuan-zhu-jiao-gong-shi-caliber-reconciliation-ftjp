from contextlib import contextmanager
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from .config import DATABASE_URL

@contextmanager
def get_conn():
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    migration = Path(__file__).resolve().parents[1] / "migrations/001_schema.sql"
    sql = migration.read_text()
    with get_conn() as conn:
        conn.execute(sql)
