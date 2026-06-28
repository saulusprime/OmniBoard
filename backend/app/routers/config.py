"""Configurazione pubblica: i parametri che servono al frontend (no autenticazione)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import settings_service
from ..database import get_db

router = APIRouter(tags=["config"])


@router.get("/config")
def public_config(db: Session = Depends(get_db)):
    return {
        "site_name": settings_service.get(db, "general.site_name"),
        "ai_move_delay_ms": settings_service.get(db, "ai.move_delay_ms"),
    }
