"""Interfaccia super admin: lettura e modifica dei parametri di programma.

La lettura dei parametri è aperta; la modifica richiede l'header ``X-Admin-Token``
uguale alla variabile d'ambiente ``ADMIN_TOKEN`` impostata sul server.
"""

from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .. import ai_providers, jobqueue, schemas, settings_service, sparring
from ..database import get_db
from ..opponents import stockfish

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(x_admin_token: str = Header(default="", alias="X-Admin-Token")) -> None:
    expected = os.getenv("ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN non configurato sul server")
    # Confronto in tempo costante: evita di rivelare il token tramite timing attack.
    if not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Token super admin non valido")


@router.get("/jobs")
def job_queue_status():
    """Introspezione della coda delle mosse IA: worker, code, contatori."""
    return jobqueue.snapshot()


@router.get("/settings")
def list_settings(db: Session = Depends(get_db)):
    return settings_service.get_all(db)


@router.put("/settings", dependencies=[Depends(require_admin)])
def update_settings(payload: schemas.SettingsUpdate, db: Session = Depends(get_db)):
    try:
        settings_service.update_many(db, payload.values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return settings_service.get_all(db)


# ----- Provider IA (login/token verso Qwen, Claude, …) -----
def _providers_payload(db: Session) -> dict:
    return {
        "providers": ai_providers.list_providers(db),
        "active": settings_service.get(db, "ai.provider"),
    }


@router.get("/ai-providers")
def list_ai_providers(db: Session = Depends(get_db)):
    return _providers_payload(db)


@router.put("/ai-providers", dependencies=[Depends(require_admin)])
def update_ai_providers(payload: schemas.AiProvidersUpdate, db: Session = Depends(get_db)):
    ai_providers.update_providers(db, payload.active, payload.providers)
    return _providers_payload(db)


@router.post("/ai-providers/{code}/test", dependencies=[Depends(require_admin)])
def test_ai_provider(code: str, db: Session = Depends(get_db)):
    ok, detail = ai_providers.test_provider(db, code)
    return {"ok": ok, "detail": detail}


# ----- Avversario Stockfish -----
@router.post("/stockfish/test", dependencies=[Depends(require_admin)])
def test_stockfish(db: Session = Depends(get_db)):
    """Verifica che il binario di Stockfish configurato risponda al protocollo UCI.

    Riporta anche il percorso effettivamente risolto (parametro, STOCKFISH_PATH o
    ricerca nel PATH), così l'esito è interpretabile.
    """
    cfg = stockfish.get_config(db)
    ok, detail = stockfish.verify(cfg)
    return {"ok": ok, "detail": detail, "path": cfg["path"]}


# ----- Sparring: il motore interno contro Stockfish, per misurarne l'Elo -----
@router.post("/sparring", dependencies=[Depends(require_admin)])
def start_sparring(payload: schemas.SparringIn, db: Session = Depends(get_db)):
    """Avvia un match motore-interno vs Stockfish (preset con Elo noto)."""
    cfg = stockfish.get_config(db)
    ok, detail = sparring.start(cfg, payload.level, payload.games, payload.engine_ms)
    if not ok:
        raise HTTPException(status_code=409, detail=detail)
    return {"started": True, "detail": detail}


@router.get("/sparring")
def sparring_state():
    """Stato del match (il client fa polling: running → done con la stima Elo)."""
    return sparring.state()
