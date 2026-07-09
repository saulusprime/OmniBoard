"""Endpoint delle sfide gruppo-vs-gruppo (squadre a tavoliere multiplo).

Propone e risponde solo chi ha i gradi (founder/admin) del gruppo giusto; le
formazioni e le partite nascono all'accettazione (v. ``group_matches.start``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import group_matches, models, notifications
from ..database import get_db
from ..i18n import _
from .auth import session_from_token

router = APIRouter(prefix="/group-matches", tags=["group-matches"])


class GroupMatchCreate(BaseModel):
    game_code: str
    challenger_group_id: int
    opponent_group_id: int
    boards: int = 2


def _actor(db: Session, token: str) -> models.User:
    return db.get(models.User, session_from_token(db, token).user_id)


def _get(db: Session, match_id: int) -> models.GroupMatch:
    match = db.get(models.GroupMatch, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail=_("Sfida di gruppo non trovata"))
    return match


def _view(db: Session, match: models.GroupMatch, detail: bool = False) -> dict:
    a, b = group_matches.points(match)
    out = {
        "id": match.id,
        "game_code": match.game.code,
        "game_name": match.game.name,
        "challenger_group_id": match.challenger_group_id,
        "challenger_group": match.challenger_group.name,
        "opponent_group_id": match.opponent_group_id,
        "opponent_group": match.opponent_group.name,
        "boards": match.boards,
        "status": match.status,
        "created_by": match.created_by,
        "points": {"challenger": a, "opponent": b},
        "winner_group": match.winner_group.name if match.winner_group else None,
        "created_at": match.created_at.isoformat() if match.created_at else None,
    }
    if detail:
        out["board_rows"] = [
            {
                "board": row.board,
                "x_user_id": row.x_user_id,
                "x_alias": row.x_user.alias,
                "o_user_id": row.o_user_id,
                "o_alias": row.o_user.alias,
                "session_id": row.session_id,
                "result": row.result,
            }
            for row in sorted(match.board_rows, key=lambda r: r.board)
        ]
    return out


@router.post("", status_code=201)
def create_match(
    payload: GroupMatchCreate,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Un manager dello SFIDANTE propone; i manager dello sfidato sono notificati."""
    actor = _actor(db, x_auth_token)
    game_row = db.query(models.Game).filter_by(code=payload.game_code).first()
    if game_row is None:
        raise HTTPException(status_code=404, detail=_("Gioco non trovato"))
    challenger = db.get(models.Group, payload.challenger_group_id)
    opponent = db.get(models.Group, payload.opponent_group_id)
    if challenger is None or opponent is None:
        raise HTTPException(status_code=404, detail="Gruppo non trovato")
    if challenger.id == opponent.id:
        raise HTTPException(status_code=400, detail=_("Un gruppo non può sfidare sé stesso"))
    if not group_matches.is_manager(db, challenger.id, actor.id):
        raise HTTPException(
            status_code=403, detail=_("Servono i gradi di fondatore o admin del gruppo")
        )
    if not group_matches.MIN_BOARDS <= payload.boards <= group_matches.MAX_BOARDS:
        raise HTTPException(
            status_code=400,
            detail=_("I tavolieri vanno da {lo} a {hi}").format(
                lo=group_matches.MIN_BOARDS, hi=group_matches.MAX_BOARDS
            ),
        )
    pending = (
        db.query(models.GroupMatch)
        .filter_by(
            challenger_group_id=challenger.id,
            opponent_group_id=opponent.id,
            status="pending",
        )
        .first()
    )
    if pending:
        raise HTTPException(status_code=409, detail=_("C'è già una sfida in attesa"))
    match = models.GroupMatch(
        game_id=game_row.id,
        challenger_group_id=challenger.id,
        opponent_group_id=opponent.id,
        boards=payload.boards,
        created_by=actor.id,
    )
    db.add(match)
    db.flush()
    # La formazione dello sfidante deve esistere GIÀ alla proposta.
    if len(group_matches.lineup(db, match, challenger.id)) < match.boards:
        raise HTTPException(
            status_code=409,
            detail=_("Il tuo gruppo non ha abbastanza membri per {n} tavolieri").format(
                n=match.boards
            ),
        )
    for uid in group_matches.managers_of(db, opponent.id):
        notifications.notify(
            db,
            uid,
            "team_challenge",
            challenger=challenger.name,
            opponent=opponent.name,
            game=game_row.name,
            boards=match.boards,
            match_id=match.id,
            group_id=opponent.id,
        )
    db.commit()
    db.refresh(match)
    return _view(db, match)


@router.get("")
def list_matches(group_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(models.GroupMatch)
    if group_id is not None:
        q = q.filter(
            (models.GroupMatch.challenger_group_id == group_id)
            | (models.GroupMatch.opponent_group_id == group_id)
        )
    rows = q.order_by(models.GroupMatch.id.desc()).all()
    out = {"matches": [_view(db, m) for m in rows]}
    if group_id is not None:
        out["record"] = group_matches.record(db, group_id)
    return out


@router.get("/{match_id}")
def match_detail(match_id: int, db: Session = Depends(get_db)):
    return _view(db, _get(db, match_id), detail=True)


@router.post("/{match_id}/accept")
def accept_match(
    match_id: int,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Un manager dello SFIDATO accetta: formazioni per Elo e partite ai tavoli."""
    actor = _actor(db, x_auth_token)
    match = _get(db, match_id)
    if match.status != "pending":
        raise HTTPException(status_code=409, detail=_("Sfida già conclusa"))
    if not group_matches.is_manager(db, match.opponent_group_id, actor.id):
        raise HTTPException(
            status_code=403, detail=_("Servono i gradi di fondatore o admin del gruppo")
        )
    for gid in (match.challenger_group_id, match.opponent_group_id):
        if len(group_matches.lineup(db, match, gid)) < match.boards:
            raise HTTPException(
                status_code=409,
                detail=_("Formazioni incomplete per {n} tavolieri").format(n=match.boards),
            )
    group_matches.start(db, match)
    db.commit()
    db.refresh(match)
    return _view(db, match, detail=True)


@router.post("/{match_id}/decline")
def decline_match(
    match_id: int,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    actor = _actor(db, x_auth_token)
    match = _get(db, match_id)
    if match.status != "pending":
        raise HTTPException(status_code=409, detail=_("Sfida già conclusa"))
    if not group_matches.is_manager(db, match.opponent_group_id, actor.id):
        raise HTTPException(
            status_code=403, detail=_("Servono i gradi di fondatore o admin del gruppo")
        )
    match.status = "declined"
    for uid in group_matches.managers_of(db, match.challenger_group_id):
        notifications.notify(
            db,
            uid,
            "team_declined",
            opponent=match.opponent_group.name,
            game=match.game.name,
            match_id=match.id,
        )
    db.commit()
    return _view(db, match)


@router.post("/{match_id}/cancel")
def cancel_match(
    match_id: int,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Un manager dello SFIDANTE ritira la proposta ancora pendente."""
    actor = _actor(db, x_auth_token)
    match = _get(db, match_id)
    if match.status != "pending":
        raise HTTPException(status_code=409, detail=_("Sfida già conclusa"))
    if not group_matches.is_manager(db, match.challenger_group_id, actor.id):
        raise HTTPException(
            status_code=403, detail=_("Servono i gradi di fondatore o admin del gruppo")
        )
    match.status = "cancelled"
    db.commit()
    return _view(db, match)
