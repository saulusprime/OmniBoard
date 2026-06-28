"""Registrazione manuale del risultato di una partita (aggiorna i punteggi).

Usato per inserire esiti senza giocare nel browser. Per le partite giocate vedi il
router ``sessions``. La logica dei punti è condivisa in ``services``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..database import get_db

router = APIRouter(prefix="/matches", tags=["matches"])


@router.post("", status_code=201)
def record_match(payload: schemas.MatchResult, db: Session = Depends(get_db)):
    game = db.query(models.Game).filter_by(code=payload.game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Gioco non trovato")
    a = db.get(models.User, payload.player_a)
    b = db.get(models.User, payload.player_b)
    if not a or not b:
        raise HTTPException(status_code=404, detail="Giocatore non trovato")
    if payload.player_a == payload.player_b:
        raise HTTPException(status_code=400, detail="I giocatori devono essere diversi")

    if payload.result == "a":
        services.award(db, a.id, game.id, "win")
        services.award(db, b.id, game.id, "loss")
    elif payload.result == "b":
        services.award(db, b.id, game.id, "win")
        services.award(db, a.id, game.id, "loss")
    else:  # draw
        services.award(db, a.id, game.id, "draw")
        services.award(db, b.id, game.id, "draw")

    db.commit()
    return {
        "game": game.code,
        "result": payload.result,
        "scores": {
            a.alias: services.score_for(db, a.id, game.id).points,
            b.alias: services.score_for(db, b.id, game.id).points,
        },
    }
