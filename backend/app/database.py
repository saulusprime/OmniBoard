"""Configurazione del database e della sessione SQLAlchemy.

In sviluppo si usa SQLite; in produzione si può puntare a PostgreSQL impostando
la variabile d'ambiente ``DATABASE_URL``.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./omniboard.db")

# SQLite richiede check_same_thread=False per essere usato dal server; il timeout è il
# busy-timeout in secondi (il worker IA in background scrive da un altro thread).
connect_args = (
    {"check_same_thread": False, "timeout": 15} if DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base dichiarativa tipizzata (SQLAlchemy 2.0: Mapped[]/mapped_column)."""


def get_db():
    """Dependency FastAPI: fornisce una sessione e la chiude a fine richiesta."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
