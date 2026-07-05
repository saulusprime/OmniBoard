"""Test delle migrazioni Alembic: unica fonte dello schema del database.

Il test di allineamento è il guardiano del workflow: se si tocca un modello
senza generare la migrazione corrispondente, fallisce elencando le differenze.
"""

import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app import models  # noqa: F401 — registra tutte le tabelle su Base.metadata
from app.database import Base
from app.db_migrate import _config, run_migrations
from sqlalchemy import create_engine, inspect


def _tmp_url(name: str) -> str:
    tmp = tempfile.mkdtemp(prefix="scacchi-migrazioni-")
    return f"sqlite:///{Path(tmp) / name}"


def test_migrations_match_models():
    """Un DB migrato da zero deve coincidere ESATTAMENTE con i modelli correnti."""
    url = _tmp_url("fresh.db")
    run_migrations(url)
    engine = create_engine(url)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"render_as_batch": True})
        diffs = compare_metadata(ctx, Base.metadata)
    engine.dispose()
    assert diffs == [], (
        "Modelli e migrazioni disallineati: genera una revisione con "
        f"`alembic revision --autogenerate`. Differenze: {diffs}"
    )


def test_legacy_create_all_db_is_adopted():
    """Un DB dell'era create_all (schema = baseline 0001) viene adottato e migrato.

    Lo si ricostruisce fedelmente: DB vuoto portato alla revisione 0001 e privato
    della tabella ``alembic_version`` — è esattamente ciò che create_all produceva
    quando l'era si è chiusa. L'adozione deve marcarlo 0001 e POI applicare le
    revisioni successive (qui la 0002: presenza online e partite a distanza).
    """
    url = _tmp_url("legacy.db")
    command.upgrade(_config(url), "0001")
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.exec_driver_sql("DROP TABLE alembic_version")
        conn.commit()
    engine.dispose()

    run_migrations(url)  # adozione (stamp 0001) + upgrade fino a head

    engine = create_engine(url)
    insp = inspect(engine)
    assert insp.has_table("alembic_version")  # da qui in poi è un DB migrato
    cols = {c["name"] for c in insp.get_columns("users")}
    assert "last_seen_at" in cols  # la 0002 è stata applicata dopo l'adozione
    engine.dispose()


def test_older_db_is_refused_with_clear_error():
    """Un DB più vecchio della baseline non viene toccato: errore esplicito."""
    url = _tmp_url("old.db")
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        conn.commit()
    engine.dispose()

    with pytest.raises(RuntimeError, match="baseline"):
        run_migrations(url)
