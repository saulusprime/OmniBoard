"""Endpoint per il catalogo dei giochi."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/games", tags=["games"])


@router.get("", response_model=list[schemas.GameOut])
def list_games(db: Session = Depends(get_db)):
    return db.query(models.Game).order_by(models.Game.name).all()
