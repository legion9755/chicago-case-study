"""
backend/database.py
SQLAlchemy 2.0 engine, session factory and declarative Base for the SQLite database.

The database is a single file:  db/chicago_crime.db
(override with the CRIME_DB_PATH environment variable).
"""
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
DB_PATH = Path(os.getenv("CRIME_DB_PATH", PROJECT_DIR / "db" / "chicago_crime.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DB_URL = f"sqlite:///{DB_PATH.as_posix()}"

engine = create_engine(DB_URL, echo=False)


@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_connection, _record):
    """SQLite ignores FOREIGN KEY constraints unless this pragma is set on every connection."""
    cur = dbapi_connection.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    cur.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Parent class of all ORM models."""
