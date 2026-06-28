"""Classifiche: universale (gamification) e per gioco con ambito geografico."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/rankings", tags=["rankings"])


def _entry(rank: int, user: models.User, points: float) -> schemas.RankingEntry:
    return schemas.RankingEntry(
        rank=rank,
        user_id=user.id,
        alias=user.alias,
        full_name=f"{user.first_name} {user.last_name}",
        nationality=user.nationality,
        region=user.region,
        points=points,
    )


@router.get("/universal", response_model=list[schemas.RankingEntry])
def universal_ranking(limit: int = Query(default=100, le=1000), db: Session = Depends(get_db)):
    """Somma dei punti di ogni utente su tutti i giochi, in ordine decrescente."""
    users = db.query(models.User).all()
    ranked = sorted(users, key=lambda u: u.universal_points, reverse=True)
    return [_entry(i, u, u.universal_points) for i, u in enumerate(ranked[:limit], 1)]


@router.get("/games/{game_code}", response_model=list[schemas.RankingEntry])
def game_ranking(
    game_code: str,
    scope: str = Query(default="global", pattern="^(global|national|regional)$"),
    country: Optional[str] = None,
    region: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db),
):
    """Classifica di un singolo gioco, filtrabile per ambito geografico.

    - ``global``: tutti i giocatori.
    - ``national``: filtrata per ``country`` (nazionalità).
    - ``regional``: filtrata per ``region``.
    """
    game = db.query(models.Game).filter_by(code=game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Gioco non trovato")

    scores = (
        db.query(models.Score)
        .filter(models.Score.game_id == game.id)
        .order_by(models.Score.points.desc())
        .all()
    )

    result: list[schemas.RankingEntry] = []
    rank = 0
    for s in scores:
        u = s.user
        if scope == "national" and (country or "") and u.nationality != country:
            continue
        if scope == "regional" and (region or "") and u.region != region:
            continue
        rank += 1
        result.append(_entry(rank, u, s.points))
        if rank >= limit:
            break
    return result
