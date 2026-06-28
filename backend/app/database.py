"""Configurazione del database e della sessione SQLAlchemy.

In sviluppo si usa SQLite; in produzione si può puntare a PostgreSQL impostando
la variabile d'ambiente ``DATABASE_URL``.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./scacchi.db")

# SQLite richiede check_same_thread=False per essere usato dal server.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency FastAPI: fornisce una sessione e la chiude a fine richiesta."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
