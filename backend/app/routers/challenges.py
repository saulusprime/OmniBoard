"""Inviti a giocare (sfide): la partita nasce quando lo sfidato accetta.

Prima la sfida a distanza creava la sessione D'UFFICIO (lo sfidato se la
trovava fra le partite); qui diventa un invito: chi lo riceve viene NOTIFICATO
e può accettare (nasce la GameSession a distanza coi parametri scelti dallo
sfidante) o rifiutare. La cadenza è validata ALLA CREAZIONE dell'invito, così
l'accettazione non può fallire per parametri sbagliati.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine import get_game

from .. import gameplay, models, notifications
from ..database import get_db
from ..i18n import _
from .auth import session_from_token

router = APIRouter(prefix="/challenges", tags=["challenges"])


class ChallengeCreate(BaseModel):
    game_code: str
    to_user_id: int
    side: str = "x"  # il lato dello SFIDANTE (x = primo a muovere/Bianco)
    time_category: str | None = None
    time_base_min: int | None = None
    time_inc_s: int = 0


def _actor(db: Session, token: str) -> models.User:
    return db.get(models.User, session_from_token(db, token).user_id)


def _view(inv: models.GameInvite) -> dict:
    return {
        "id": inv.id,
        "game_code": inv.game.code,
        "game_name": inv.game.name,
        "from_user_id": inv.from_user_id,
        "from_alias": inv.from_user.alias,
        "to_user_id": inv.to_user_id,
        "to_alias": inv.to_user.alias,
        "side": inv.side,
        "time_category": inv.tc_category,
        "time_base_min": inv.tc_base_min,
        "time_inc_s": inv.tc_inc_s,
        "status": inv.status,
        "session_id": inv.session_id,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
    }


def _get_pending(db: Session, invite_id: int) -> models.GameInvite:
    inv = db.get(models.GameInvite, invite_id)
    if inv is None:
        raise HTTPException(status_code=404, detail=_("Sfida non trovata"))
    if inv.status != "pending":
        raise HTTPException(status_code=409, detail=_("Sfida già conclusa"))
    return inv


@router.post("", status_code=201)
def create_challenge(
    payload: ChallengeCreate,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    actor = _actor(db, x_auth_token)
    game_row = db.query(models.Game).filter_by(code=payload.game_code).first()
    if game_row is None:
        raise HTTPException(status_code=404, detail=_("Gioco non trovato"))
    target = db.get(models.User, payload.to_user_id)
    if target is None:
        raise HTTPException(status_code=404, detail=_("Utente non trovato"))
    if target.id == actor.id:
        raise HTTPException(status_code=400, detail=_("Non puoi sfidare te stesso"))
    if payload.side not in ("x", "o"):
        raise HTTPException(status_code=400, detail=_("Lato sconosciuto (x oppure o)"))
    # La cadenza si valida SUBITO: un invito accettabile non fallisce mai dopo.
    try:
        gameplay.build_time_control(
            payload.game_code, payload.time_category, payload.time_base_min, payload.time_inc_s
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    duplicate = (
        db.query(models.GameInvite)
        .filter_by(
            from_user_id=actor.id,
            to_user_id=target.id,
            game_id=game_row.id,
            status="pending",
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail=_("Hai già una sfida in attesa"))
    inv = models.GameInvite(
        game_id=game_row.id,
        from_user_id=actor.id,
        to_user_id=target.id,
        side=payload.side,
        tc_category=payload.time_category,
        tc_base_min=payload.time_base_min,
        tc_inc_s=payload.time_inc_s,
        status="pending",
    )
    db.add(inv)
    db.flush()
    notifications.notify(
        db,
        target.id,
        "game_invite",
        alias=actor.alias,
        game=game_row.name,
        invite_id=inv.id,
    )
    db.commit()
    db.refresh(inv)
    return _view(inv)


@router.get("/mine")
def my_challenges(
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Le sfide PENDENTI dell'utente: ricevute (da accettare) e inviate (in attesa)."""
    actor = _actor(db, x_auth_token)
    rows = (
        db.query(models.GameInvite)
        .filter(
            models.GameInvite.status == "pending",
            (models.GameInvite.from_user_id == actor.id)
            | (models.GameInvite.to_user_id == actor.id),
        )
        .order_by(models.GameInvite.id.desc())
        .all()
    )
    return {
        "incoming": [_view(i) for i in rows if i.to_user_id == actor.id],
        "outgoing": [_view(i) for i in rows if i.from_user_id == actor.id],
    }


@router.post("/{invite_id}/accept")
def accept_challenge(
    invite_id: int,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Lo sfidato accetta: nasce la partita A DISTANZA coi parametri dell'invito."""
    actor = _actor(db, x_auth_token)
    inv = _get_pending(db, invite_id)
    if inv.to_user_id != actor.id:
        raise HTTPException(status_code=403, detail=_("La sfida non è per te"))
    game = get_game(inv.game.code)
    time_control = gameplay.build_time_control(
        inv.game.code, inv.tc_category, inv.tc_base_min, inv.tc_inc_s or 0
    )
    x_uid = inv.from_user_id if inv.side == "x" else inv.to_user_id
    o_uid = inv.to_user_id if inv.side == "x" else inv.from_user_id
    state = game.initial_state()
    session = models.GameSession(
        game_id=inv.game_id,
        x_user_id=x_uid,
        o_user_id=o_uid,
        x_is_ai=False,
        o_is_ai=False,
        remote=True,
        state_json=json.dumps(game.serialize_state(state)),
        moves_json="[]",
        status="in_progress",
    )
    gameplay.init_clock(session, time_control)
    db.add(session)
    db.flush()
    inv.status = "accepted"
    inv.session_id = session.id
    notifications.notify(
        db,
        inv.from_user_id,
        "invite_accepted",
        alias=actor.alias,
        game=inv.game.name,
        session_id=session.id,
    )
    db.commit()
    gameplay.resolve_chance(db, game, session)  # giochi col caso: il server tira
    db.refresh(inv)
    return _view(inv)


@router.post("/{invite_id}/decline")
def decline_challenge(
    invite_id: int,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    actor = _actor(db, x_auth_token)
    inv = _get_pending(db, invite_id)
    if inv.to_user_id != actor.id:
        raise HTTPException(status_code=403, detail=_("La sfida non è per te"))
    inv.status = "declined"
    notifications.notify(
        db, inv.from_user_id, "invite_declined", alias=actor.alias, game=inv.game.name
    )
    db.commit()
    return _view(inv)


@router.post("/{invite_id}/cancel")
def cancel_challenge(
    invite_id: int,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Lo SFIDANTE ritira una sfida ancora pendente (nessuna notifica: non serve)."""
    actor = _actor(db, x_auth_token)
    inv = _get_pending(db, invite_id)
    if inv.from_user_id != actor.id:
        raise HTTPException(status_code=403, detail=_("Puoi ritirare solo le tue sfide"))
    inv.status = "cancelled"
    db.commit()
    return _view(inv)
