"""Endpoint del tutorial (istruzione guidata): lezioni e progressi.

- ``GET /lessons`` — l'indice delle lezioni per gioco; con ``X-Auth-Token``
  include il progresso personale (riprendi da dove eri, lezioni completate).
- ``GET /lessons/{code}`` — la lezione completa, passo per passo.
- ``POST /lessons/{code}/progress`` — salva il passo raggiunto (autenticato);
  quando l'allievo supera l'ultimo passo la lezione risulta completata.

Le lezioni si possono SEGUIRE anche da anonimi (lettura aperta): solo il
salvataggio del progresso richiede l'accesso.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine import get_game

from .. import lessons, models
from ..database import get_db
from ..i18n import _
from .auth import session_from_token

router = APIRouter(prefix="/lessons", tags=["lessons"])


def _localized_steps(lesson: dict) -> list[dict]:
    """I passi con i testi nella lingua della richiesta.

    Costruisce COPIE: la cache delle lezioni (``all_lessons``) resta italiana
    e la stessa lezione può essere servita in lingue diverse a client diversi.
    """
    steps = []
    for s in lesson["steps"]:
        task = s.get("task")
        if task:
            task = {**task, "prompt": _(task["prompt"]), "success": _(task["success"])}
        steps.append({**s, "text": _(s["text"]), "task": task})
    return steps


class ProgressIn(BaseModel):
    step: int  # ultimo passo raggiunto (0-based)
    completed: bool = False


def _progress_map(db: Session, token: str) -> dict[str, models.LessonProgress]:
    """Progressi dell'utente del token; vuoto se il token manca (anonimo)."""
    if not token:
        return {}
    user = session_from_token(db, token).user  # 401 se il token è scaduto/errato
    rows = db.query(models.LessonProgress).filter_by(user_id=user.id).all()
    return {r.lesson_code: r for r in rows}


@router.get("")
def list_lessons(
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Indice delle lezioni (ordinate per gioco e grado), con progresso personale."""
    progress = _progress_map(db, x_auth_token)
    out = []
    for lesson in lessons.all_lessons():
        p = progress.get(lesson["code"])
        out.append(
            {
                "code": lesson["code"],
                "game_code": lesson["game_code"],
                "game_name": get_game(lesson["game_code"]).name,
                "title": _(lesson["title"]),
                "order": lesson["order"],
                "steps_count": len(lesson["steps"]),
                "progress": ({"last_step": p.last_step, "completed": p.completed} if p else None),
            }
        )
    return {"lessons": out}


@router.get("/{code}")
def get_lesson(
    code: str,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """La lezione completa: passi, posizioni, evidenziazioni e mosse richieste."""
    lesson = lessons.get_lesson(code)
    if lesson is None:
        raise HTTPException(status_code=404, detail=_("Lezione non trovata"))
    game = get_game(lesson["game_code"])
    p = _progress_map(db, x_auth_token).get(code)
    return {
        "code": lesson["code"],
        "game_code": lesson["game_code"],
        "game_name": game.name,
        "title": _(lesson["title"]),
        # Dimensioni e tipo della griglia: il client disegna la scacchiera
        # con lo stesso stile della pagina di gioco (case, pezzi pieni, temi).
        "rows": game.rows,
        "cols": game.cols,
        "move_type": game.move_type,
        "steps": _localized_steps(lesson),
        "progress": {"last_step": p.last_step, "completed": p.completed} if p else None,
    }


@router.post("/{code}/progress")
def save_progress(
    code: str,
    payload: ProgressIn,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Salva il progresso dell'allievo (richiede l'accesso).

    ``last_step`` non regredisce mai (tornare indietro per ripassare non
    cancella i passi già raggiunti) e ``completed`` è definitivo.
    """
    lesson = lessons.get_lesson(code)
    if lesson is None:
        raise HTTPException(status_code=404, detail=_("Lezione non trovata"))
    user = session_from_token(db, x_auth_token).user
    step = max(0, min(int(payload.step), len(lesson["steps"]) - 1))
    row = db.query(models.LessonProgress).filter_by(user_id=user.id, lesson_code=code).first()
    if row is None:
        row = models.LessonProgress(user_id=user.id, lesson_code=code, last_step=step)
        db.add(row)
    was_completed = bool(row.completed)
    row.last_step = max(row.last_step, step)
    row.completed = bool(row.completed or payload.completed)
    if row.completed and not was_completed:
        # Lezione finita per la prima volta: gettoni (ref = codice lezione).
        from .. import settings_service, wallet

        wallet.award(
            db,
            user.id,
            int(settings_service.get(db, "coins.lesson")),
            "lesson_completed",
            f"lesson:{code}",
        )
    db.commit()
    return {"last_step": row.last_step, "completed": row.completed}
