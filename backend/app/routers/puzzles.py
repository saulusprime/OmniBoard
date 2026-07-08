"""API del sistema puzzle: catalogo, esecuzione libera, generazione dai blunder."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine import get_game

from .. import models, puzzles
from ..database import get_db
from ..i18n import _
from .auth import session_from_token

router = APIRouter(prefix="/puzzles", tags=["puzzles"])


def _me(db: Session, token: str) -> int | None:
    """Utente dal token, se presente (i puzzle si giocano anche da anonimi)."""
    if not token:
        return None
    try:
        return session_from_token(db, token).user.id
    except HTTPException:
        return None


@router.get("")
def list_puzzles(
    theme: str | None = Query(default=None),
    difficulty: int | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Catalogo dei puzzle (filtri per tema/difficoltà; progressi se loggato)."""
    q = db.query(models.Puzzle)
    if theme:
        q = q.filter(models.Puzzle.theme == theme)
    if difficulty:
        q = q.filter(models.Puzzle.difficulty == difficulty)
    rows = q.order_by(models.Puzzle.id.asc()).limit(limit).all()
    solved: dict[int, bool] = {}
    user_id = _me(db, x_auth_token)
    if user_id:
        for a in db.query(models.PuzzleAttempt).filter_by(user_id=user_id).all():
            solved[a.puzzle_id] = a.solved
    themes = sorted({r.theme for r in db.query(models.Puzzle.theme).distinct()})
    return {
        "themes": [t[0] if isinstance(t, tuple) else t for t in themes],
        "puzzles": [
            {
                "id": r.id,
                "theme": r.theme,
                "difficulty": r.difficulty,
                "source": r.source,
                "steps": (len(json.loads(r.solution_json)) + 1) // 2,
                "solved": solved.get(r.id),
            }
            for r in rows
        ],
    }


@router.get("/{puzzle_id}")
def puzzle_detail(puzzle_id: int, step: int = 0, db: Session = Depends(get_db)):
    puzzle = db.get(models.Puzzle, puzzle_id)
    if puzzle is None:
        raise HTTPException(status_code=404, detail=_("Puzzle non trovato"))
    view = puzzles.puzzle_view(get_game("chess"), puzzle, step)
    if view is None:
        raise HTTPException(status_code=400, detail=_("Semimossa inesistente"))
    return view


class AttemptIn(BaseModel):
    step: int = 0
    move: str


@router.post("/{puzzle_id}/attempt")
def attempt(
    puzzle_id: int,
    payload: AttemptIn,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Verifica una mossa del solutore; registra il progresso se loggato."""
    puzzle = db.get(models.Puzzle, puzzle_id)
    if puzzle is None:
        raise HTTPException(status_code=404, detail=_("Puzzle non trovato"))
    result = puzzles.check_attempt(get_game("chess"), puzzle, payload.step, payload.move)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    user_id = _me(db, x_auth_token)
    if user_id:
        puzzles.record_attempt(db, user_id, puzzle_id, bool(result.get("solved")))
    return result


@router.post("/generate")
def generate(
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Genera puzzle dai blunder delle PROPRIE partite analizzate (serve il login)."""
    user_id = _me(db, x_auth_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail=_("Sessione non valida o scaduta"))
    created = puzzles.generate_from_games(db, user_id=user_id)
    return {"created": created}
