"""Endpoint per l'anagrafica giocatori."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import chess_profile, models, schemas, settings_service
from ..database import get_db
from ..security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=schemas.UserOut, status_code=201)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    if not settings_service.get(db, "users.allow_registration"):
        raise HTTPException(
            status_code=403, detail="Registrazioni disabilitate dall'amministratore"
        )
    if db.query(models.User).filter(models.User.alias == payload.alias).first():
        raise HTTPException(status_code=409, detail="Alias già in uso")
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email già registrata")

    user = models.User(
        first_name=payload.first_name,
        last_name=payload.last_name,
        alias=payload.alias,
        email=payload.email,
        nationality=payload.nationality,
        region=payload.region,
        password_hash=hash_password(payload.password) if payload.password else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).order_by(models.User.alias).all()


@router.get("/{user_id}", response_model=schemas.UserDetail)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    scores = [
        schemas.ScoreOut(
            game_code=s.game.code,
            game_name=s.game.name,
            points=s.points,
            matches_played=s.matches_played,
            wins=s.wins,
            draws=s.draws,
            losses=s.losses,
        )
        for s in user.scores
    ]
    return schemas.UserDetail(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        alias=user.alias,
        email=user.email,
        nationality=user.nationality,
        region=user.region,
        created_at=user.created_at,
        universal_points=user.universal_points,
        scores=scores,
    )


@router.get("/{user_id}/chess-profile")
def chess_profile_endpoint(user_id: int, db: Session = Depends(get_db)):
    """Profilo scacchistico del giocatore: schemi (aperture), debolezze e stile derivato.

    È ciò che l'IA usa per adattare il proprio gioco quando affronta questo avversario.
    """
    profile = chess_profile.build_profile(db, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    return profile


@router.get("/{user_id}/history")
def user_history(user_id: int, db: Session = Depends(get_db)):
    """Storico delle partite concluse del giocatore, con il log delle mosse."""
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")

    sessions = (
        db.query(models.GameSession)
        .filter(
            (models.GameSession.x_user_id == user_id) | (models.GameSession.o_user_id == user_id),
            models.GameSession.status == "finished",
        )
        .order_by(models.GameSession.created_at.desc())
        .all()
    )

    history = []
    for s in sessions:
        your_side = "x" if s.x_user_id == user_id else "o"
        if s.winner == "draw":
            result = "draw"
        elif s.winner == your_side:
            result = "win"
        else:
            result = "loss"
        if your_side == "x":
            opponent = "IA" if s.o_is_ai else (s.o_user.alias if s.o_user else "—")
        else:
            opponent = "IA" if s.x_is_ai else (s.x_user.alias if s.x_user else "—")
        history.append(
            {
                "session_id": s.id,
                "game_code": s.game.code,
                "game_name": s.game.name,
                "date": s.created_at,
                "your_side": your_side,
                "opponent": opponent,
                "result": result,
                "moves": json.loads(s.moves_json or "[]"),
            }
        )
    return history
