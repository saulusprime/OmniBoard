"""Endpoint per l'anagrafica giocatori."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=schemas.UserOut, status_code=201)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
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
