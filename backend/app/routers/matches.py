"""Registrazione dei risultati delle partite e aggiornamento dei punteggi.

Schema punti (provvisorio): vittoria +3, patta +1, sconfitta +0. In futuro questa
logica potrà essere sostituita da un sistema di rating (es. Elo) e collegata al
motore di gioco quando le partite saranno gestite end-to-end.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/matches", tags=["matches"])

POINTS_WIN = 3.0
POINTS_DRAW = 1.0
POINTS_LOSS = 0.0


def _score_for(db: Session, user_id: int, game_id: int) -> models.Score:
    score = db.query(models.Score).filter_by(user_id=user_id, game_id=game_id).first()
    if not score:
        # Inizializza esplicitamente: i default delle colonne si applicano solo al
        # flush, mentre qui aggiorniamo gli attributi prima di salvare.
        score = models.Score(
            user_id=user_id,
            game_id=game_id,
            points=0.0,
            matches_played=0,
            wins=0,
            draws=0,
            losses=0,
        )
        db.add(score)
    return score


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

    sa = _score_for(db, a.id, game.id)
    sb = _score_for(db, b.id, game.id)
    sa.matches_played += 1
    sb.matches_played += 1

    if payload.result == "a":
        sa.points += POINTS_WIN
        sb.points += POINTS_LOSS
        sa.wins += 1
        sb.losses += 1
    elif payload.result == "b":
        sb.points += POINTS_WIN
        sa.points += POINTS_LOSS
        sb.wins += 1
        sa.losses += 1
    else:  # draw
        sa.points += POINTS_DRAW
        sb.points += POINTS_DRAW
        sa.draws += 1
        sb.draws += 1

    db.commit()
    return {
        "game": game.code,
        "result": payload.result,
        "scores": {
            a.alias: sa.points,
            b.alias: sb.points,
        },
    }
