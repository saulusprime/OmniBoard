"""Area community: presenza online e partite del giocatore.

Gamification di base:

- ``GET /community/online`` — chi è connesso adesso (badge di presenza) con il
  punteggio complessivo su tutti i giochi (badge punti). "Online" = heartbeat
  ricevuto entro la finestra ``community.online_window_s`` (parametro admin).
- ``GET /community/my-games`` — le partite in corso che riguardano il giocatore
  autenticato: è così che chi riceve una sfida a distanza la trova e la apre.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header
from sqlalchemy import or_
from sqlalchemy.orm import Session

from engine import get_game

from .. import gameplay, models, settings_service
from ..database import get_db
from .auth import session_from_token

router = APIRouter(prefix="/community", tags=["community"])


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive-UTC come le colonne


@router.get("/online")
def online_players(db: Session = Depends(get_db)):
    """Giocatori online adesso, con il punteggio complessivo (tutti i giochi)."""
    window_s = int(settings_service.get(db, "community.online_window_s"))
    cutoff = _now() - timedelta(seconds=window_s)
    users = (
        db.query(models.User)
        .filter(models.User.last_seen_at.isnot(None), models.User.last_seen_at >= cutoff)
        .order_by(models.User.alias)
        .all()
    )
    return {
        "window_s": window_s,
        "online": [
            {
                "id": u.id,
                "alias": u.alias,
                "universal_points": u.universal_points,  # badge punteggio complessivo
            }
            for u in users
        ],
    }


@router.get("/my-games")
def my_games(
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Le partite in corso del giocatore autenticato (sfide ricevute comprese).

    Per ogni partita si dice anche se tocca a lui: la lista è il "campanello"
    con cui lo sfidato scopre una nuova partita a distanza creata da altri.
    """
    me = session_from_token(db, x_auth_token).user
    sessions = (
        db.query(models.GameSession)
        .filter(
            models.GameSession.status == "in_progress",
            or_(
                models.GameSession.x_user_id == me.id,
                models.GameSession.o_user_id == me.id,
            ),
        )
        .order_by(models.GameSession.id.desc())
        .all()
    )
    out = []
    for s in sessions:
        game = get_game(s.game.code)
        state = gameplay.load_state(game, s)
        my_side = "x" if s.x_user_id == me.id else "o"
        current = "x" if game.current_player(state) == 0 else "o"
        # L'avversario può essere un umano (alias) o un motore (etichetta tipo).
        opp = s.o_user if my_side == "x" else s.x_user
        opp_kind = gameplay.side_kind(s, 1 if my_side == "x" else 0)
        out.append(
            {
                "session_id": s.id,
                "game_code": s.game.code,
                "game_name": game.name,
                "remote": bool(s.remote),
                "my_side": my_side,
                "my_turn": current == my_side,
                "opponent": opp.alias if opp else opp_kind,
            }
        )
    return {"games": out}
