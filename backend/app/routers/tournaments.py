"""Endpoint dei tornei fra giocatori umani (eliminazione diretta e gironi).

Ciclo: chi organizza CREA il torneo (aperto o riservato a un gruppo), gli
iscritti si uniscono finché è ``open``, l'organizzatore lo AVVIA; da lì le
partite compaiono in «le mie partite» degli accoppiati e il torneo avanza da
solo a ogni risultato (hook in ``finalize_session``). Il dettaglio espone il
TABELLONE per turni (knockout) e la classifica (girone).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import human_tournaments, models
from ..database import get_db
from ..i18n import _
from .auth import session_from_token

router = APIRouter(prefix="/tournaments", tags=["tournaments"])


class HumanTournamentCreate(BaseModel):
    game_code: str
    name: str
    format: str  # knockout | round_robin
    double_round: bool = False
    group_id: int | None = None


def _actor(db: Session, token: str) -> models.User:
    return db.get(models.User, session_from_token(db, token).user_id)


def _get(db: Session, tournament_id: int) -> models.HumanTournament:
    t = db.get(models.HumanTournament, tournament_id)
    if t is None:
        raise HTTPException(status_code=404, detail=_("Torneo non trovato"))
    return t


def _is_group_member(db: Session, group_id: int, user_id: int) -> bool:
    return (
        db.query(models.GroupMembership).filter_by(group_id=group_id, user_id=user_id).first()
        is not None
    )


def _view(db: Session, t: models.HumanTournament, detail: bool = False) -> dict:
    out = {
        "id": t.id,
        "name": t.name,
        "game_code": t.game.code,
        "game_name": t.game.name,
        "format": t.format,
        "double_round": t.double_round,
        "status": t.status,
        "created_by": t.created_by,
        "group_id": t.group_id,
        "group_name": t.group.name if t.group else None,
        "winner": t.winner.alias if t.winner else None,
        "players": [
            {"user_id": p.user_id, "alias": p.user.alias, "seed": p.seed}
            for p in sorted(t.players, key=lambda p: (p.seed or 10**6, p.user.alias))
        ],
        "max_players": human_tournaments.max_players(t),
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
    if not detail:
        return out
    alias_of = {p.user_id: p.user.alias for p in t.players}
    rounds: dict[int, list[dict]] = {}
    for g in sorted(t.games, key=lambda g: (g.round, g.slot)):
        rounds.setdefault(g.round, []).append(
            {
                "slot": g.slot,
                "x_user_id": g.x_user_id,
                "x_alias": alias_of.get(g.x_user_id, "?"),
                "o_user_id": g.o_user_id,
                "o_alias": alias_of.get(g.o_user_id) if g.o_user_id else None,  # None = bye
                "session_id": g.session_id,
                "result": g.result,
            }
        )
    out["rounds"] = [{"round": r, "games": games} for r, games in sorted(rounds.items())]
    if t.format == "round_robin":
        out["standings"] = human_tournaments.standings(db, t)
    return out


@router.post("", status_code=201)
def create_tournament(
    payload: HumanTournamentCreate,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Crea un torneo in stato ``open``; con ``group_id`` è riservato ai membri."""
    actor = _actor(db, x_auth_token)
    game = db.query(models.Game).filter_by(code=payload.game_code).first()
    if game is None:
        raise HTTPException(status_code=404, detail=_("Gioco non trovato"))
    if payload.format not in human_tournaments.FORMATS:
        raise HTTPException(status_code=400, detail=_("Formato di torneo sconosciuto"))
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail=_("Nome obbligatorio"))
    if payload.group_id is not None:
        if not db.get(models.Group, payload.group_id):
            raise HTTPException(status_code=404, detail="Gruppo non trovato")
        if not _is_group_member(db, payload.group_id, actor.id):
            raise HTTPException(
                status_code=403, detail=_("Solo i membri del gruppo possono organizzare")
            )
    t = models.HumanTournament(
        game_id=game.id,
        name=payload.name.strip(),
        format=payload.format,
        double_round=payload.double_round and payload.format == "round_robin",
        created_by=actor.id,
        group_id=payload.group_id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _view(db, t)


@router.get("")
def list_tournaments(
    game_code: str | None = None,
    group_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.HumanTournament).join(models.Game)
    if game_code:
        q = q.filter(models.Game.code == game_code)
    if group_id is not None:
        q = q.filter(models.HumanTournament.group_id == group_id)
    if status:
        q = q.filter(models.HumanTournament.status == status)
    rows = q.order_by(models.HumanTournament.id.desc()).all()
    return {"tournaments": [_view(db, t) for t in rows]}


@router.get("/{tournament_id}")
def tournament_detail(tournament_id: int, db: Session = Depends(get_db)):
    return _view(db, _get(db, tournament_id), detail=True)


@router.post("/{tournament_id}/join")
def join_tournament(
    tournament_id: int,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    t = _get(db, tournament_id)
    actor = _actor(db, x_auth_token)
    if t.status != "open":
        raise HTTPException(status_code=409, detail=_("Le iscrizioni sono chiuse"))
    if t.group_id is not None and not _is_group_member(db, t.group_id, actor.id):
        raise HTTPException(status_code=403, detail=_("Torneo riservato ai membri del gruppo"))
    if any(p.user_id == actor.id for p in t.players):
        raise HTTPException(status_code=409, detail=_("Sei già iscritto"))
    if len(t.players) >= human_tournaments.max_players(t):
        raise HTTPException(status_code=409, detail=_("Torneo al completo"))
    db.add(models.HumanTournamentPlayer(tournament_id=t.id, user_id=actor.id))
    db.commit()
    db.refresh(t)
    return _view(db, t)


@router.post("/{tournament_id}/leave")
def leave_tournament(
    tournament_id: int,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    t = _get(db, tournament_id)
    actor = _actor(db, x_auth_token)
    if t.status != "open":
        raise HTTPException(status_code=409, detail=_("Il torneo è già avviato"))
    p = next((p for p in t.players if p.user_id == actor.id), None)
    if p is None:
        raise HTTPException(status_code=404, detail=_("Non sei iscritto"))
    db.delete(p)
    db.commit()
    db.refresh(t)
    return _view(db, t)


@router.post("/{tournament_id}/start")
def start_tournament(
    tournament_id: int,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Solo l'organizzatore avvia; servono almeno 2 iscritti."""
    t = _get(db, tournament_id)
    actor = _actor(db, x_auth_token)
    if actor.id != t.created_by:
        raise HTTPException(status_code=403, detail=_("Solo l'organizzatore avvia il torneo"))
    if t.status != "open":
        raise HTTPException(status_code=409, detail=_("Il torneo è già avviato"))
    if len(t.players) < 2:
        raise HTTPException(status_code=409, detail=_("Servono almeno 2 iscritti"))
    human_tournaments.start(db, t)
    db.refresh(t)
    return _view(db, t, detail=True)
