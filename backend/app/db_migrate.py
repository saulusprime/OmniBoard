"""Applicazione programmatica delle migrazioni Alembic (all'avvio dell'app).

Sostituisce il vecchio ``Base.metadata.create_all``: lo schema del database ha
un'unica fonte di verità, le revisioni in ``backend/migrations/versions/``.
Un cambio di schema NON richiede più di ricreare il DB di sviluppo: si genera
una revisione (``alembic revision --autogenerate -m "..."``) e l'avvio
successivo la applica da solo.

Casi gestiti da :func:`run_migrations`:

- database nuovo → ``upgrade head`` crea tutto;
- database già migrato → ``upgrade head`` applica solo le revisioni mancanti;
- database dell'era ``create_all`` (nessuna tabella ``alembic_version``): se lo
  schema corrisponde alla baseline (revisione 0001) viene ADOTTATO con uno
  ``stamp`` e da lì in poi migrato normalmente; se è più vecchio ci si ferma
  con un errore chiaro (in sviluppo: eliminare ``backend/scacchi.db``).
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from .database import DATABASE_URL

_BACKEND_DIR = Path(__file__).resolve().parents[1]
# La revisione il cui schema coincide con l'ultimo create_all pre-Alembic:
# è il punto di adozione dei database esistenti.
_BASELINE_REV = "0001"
# URL già migrati in QUESTO processo: i test aprono l'app decine di volte
# (un lifespan per TestClient) e non serve ripassare da Alembic ogni volta.
_done: set[str] = set()


def _config(url: str) -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    # Override letto da migrations/env.py: CLI e app condividono lo stesso env.
    cfg.attributes["sqlalchemy_url"] = url
    return cfg


def _adopt_legacy_db_if_needed(url: str) -> None:
    """Riconosce (e adotta) un DB creato con create_all prima delle migrazioni."""
    engine = create_engine(url)
    try:
        insp = inspect(engine)
        if not insp.has_table("users") or insp.has_table("alembic_version"):
            return  # DB nuovo oppure già sotto Alembic: nulla da adottare
        cols = {c["name"] for c in insp.get_columns("users")}
        baseline = "is_approved" in cols and insp.has_table("auth_sessions")
        if not baseline:
            raise RuntimeError(
                "Il database esistente precede le migrazioni Alembic e non "
                "corrisponde alla baseline (revisione 0001): in sviluppo "
                "eliminarlo e riavviare (rm backend/scacchi.db)."
            )
    finally:
        engine.dispose()
    # Schema identico alla baseline: si marca la revisione senza toccare i dati.
    command.stamp(_config(url), _BASELINE_REV)


def run_migrations(url: str | None = None) -> None:
    """Porta il database alla revisione più recente (head)."""
    url = url or DATABASE_URL
    if url in _done:
        return
    _adopt_legacy_db_if_needed(url)
    command.upgrade(_config(url), "head")
    _done.add(url)
