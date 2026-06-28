"""Popolamento iniziale del catalogo dei giochi (idempotente)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from . import models

DEFAULT_GAMES = [
    {"code": "tictactoe", "name": "Tris", "is_stochastic": False},
    {"code": "connect4", "name": "Forza 4", "is_stochastic": False},
    {"code": "checkers", "name": "Dama italiana", "is_stochastic": False},
    {"code": "chess", "name": "Scacchi", "is_stochastic": False},
    {"code": "backgammon", "name": "Backgammon", "is_stochastic": True},
]


def seed_games(db: Session) -> None:
    for g in DEFAULT_GAMES:
        exists = db.query(models.Game).filter_by(code=g["code"]).first()
        if not exists:
            db.add(models.Game(**g))
    db.commit()
