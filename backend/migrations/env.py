"""Ambiente Alembic: collega le migrazioni ai modelli e al database dell'app.

L'URL del database NON sta in alembic.ini: arriva da ``app.database`` (variabile
d'ambiente ``DATABASE_URL``, caricata anche dal file .env della root — vedi
app/__init__.py), oppure può essere forzato dal chiamante programmatico
(app/db_migrate.py) tramite ``config.attributes["sqlalchemy_url"]``: è ciò che
usano i test per migrare database temporanei.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# backend/ nel sys.path anche quando Alembic è invocato da un'altra directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: F401,E402 — importa TUTTI i modelli su Base.metadata
from app.database import DATABASE_URL, Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Lo schema di riferimento per l'autogenerate: i modelli SQLAlchemy dell'app.
target_metadata = Base.metadata


def _database_url() -> str:
    """Priorità: override programmatico (test/runner) → app.database."""
    return config.attributes.get("sqlalchemy_url") or DATABASE_URL


def run_migrations_offline() -> None:
    """Modalità offline: genera SQL senza connettersi (``alembic upgrade --sql``)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # ALTER TABLE su SQLite = ricrea la tabella (batch)
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Modalità normale: si connette e applica le migrazioni."""
    url = _database_url()
    connect_args = {"timeout": 15} if url.startswith("sqlite") else {}
    engine = create_engine(url, poolclass=pool.NullPool, connect_args=connect_args)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # necessario per gli ALTER futuri su SQLite
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
