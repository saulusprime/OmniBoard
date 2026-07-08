"""Statistiche avanzate del giocatore e raccolta delle «mosse geniali».

Aggrega SOLO materia prima già in casa (mai lavoro del motore qui):

- punteggi e rating per gioco (``scores``/``ratings``);
- profilo scacchistico in cache (accuracy, colori, aperture — ``profile_cache``);
- **serie** (vittorie consecutive, migliore e corrente) per gioco;
- distribuzione degli **esiti** delle partite di scacchi (matto/tempo/abbandono/
  patta d'accordo/ripetizione);
- conteggio dei **badge di qualità** sulle PROPRIE mosse (🌟👍⚔️🐔🤔😬🤡,
  assegnati dal commentatore in ``moves_json``);
- la raccolta delle **mosse geniali**: le proprie mosse col badge 🌟
  («da maestro»), con avversario, data e aggancio alla moviola. Lo «screenshot»
  è ``GET /sessions/{id}/board.png?ply=N`` (renderer Pillow della GIF).

Nota dal TODO: il badge 💎 «geniale» (mossa migliore CHE sacrifica materiale)
non esiste ancora — quando arriverà, la raccolta lo includerà accanto ai 🌟.
"""

from __future__ import annotations

import json

from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import ai_arena, models, profile_cache, rating
from .i18n import _

CHESS_CODE = "chess"
BADGE_SYMBOLS = ("🌟", "👍", "⚔️", "🐔", "🤔", "😬", "🤡")
BRILLIANT = "🌟"


def _user_sessions(db: Session, user_id: int, game_code: str | None = None):
    q = (
        db.query(models.GameSession)
        .join(models.Game)
        .filter(
            models.GameSession.status == "finished",
            or_(
                models.GameSession.x_user_id == user_id,
                models.GameSession.o_user_id == user_id,
            ),
        )
    )
    if game_code:
        q = q.filter(models.Game.code == game_code)
    return q.order_by(models.GameSession.id.asc()).all()


def _result_for(session: models.GameSession, user_id: int) -> str:
    side = "x" if session.x_user_id == user_id else "o"
    if session.winner == "draw" or session.winner is None:
        return "draw"
    return "win" if session.winner == side else "loss"


def _opponent_label(session: models.GameSession, user_id: int) -> str:
    """Chi c'era dall'altra parte: alias umano o etichetta del concorrente IA."""
    other = 1 if session.x_user_id == user_id else 0
    user = session.x_user if other == 0 else session.o_user
    if user is not None:
        return user.alias
    identity = ai_arena.identity_of(session, other)
    return ai_arena.label_of(identity) if identity else _("sconosciuto")


def _streaks(sessions, user_id: int) -> dict:
    best = current = 0
    for s in sessions:  # in ordine cronologico
        if _result_for(s, user_id) == "win":
            current += 1
            best = max(best, current)
        else:
            current = 0
    return {"best_win_streak": best, "current_win_streak": current}


def build(db: Session, user_id: int) -> dict | None:
    """Il cruscotto delle statistiche avanzate (None se l'utente non esiste)."""
    user = db.get(models.User, user_id)
    if user is None:
        return None
    current_season = rating.season(db)
    ratings = {r["game_code"]: r for r in rating.for_user(db, user_id, current_season)}

    per_game: list[dict] = []
    for score in user.scores:
        sessions = _user_sessions(db, user_id, score.game.code)
        entry = {
            "game_code": score.game.code,
            "game_name": score.game.name,
            "points": score.points,
            "wins": score.wins,
            "draws": score.draws,
            "losses": score.losses,
            "matches": score.matches_played,
            "elo": ratings.get(score.game.code),
            **_streaks(sessions, user_id),
        }
        per_game.append(entry)

    # Scacchi: esiti e badge dalle sessioni; il resto dal profilo in cache.
    chess_sessions = _user_sessions(db, user_id, CHESS_CODE)
    finish_reasons = {"mate": 0, "time": 0, "resign": 0, "agreement": 0, "repetition": 0}
    badges = dict.fromkeys(BADGE_SYMBOLS, 0)
    my_marks = ("X", "O")
    for s in chess_sessions:
        reason = s.finish_reason or ("mate" if s.winner in ("x", "o") else "agreement")
        if s.winner == "draw" and s.finish_reason is None:
            reason = "agreement"  # patte di scacchiera senza motivo esplicito: raro
        finish_reasons[reason] = finish_reasons.get(reason, 0) + 1
        mark = "X" if s.x_user_id == user_id else "O"
        if mark not in my_marks:
            continue
        for move in json.loads(s.moves_json or "[]"):
            quality = move.get("quality")
            if quality and move.get("player") == mark and quality.get("symbol") in badges:
                badges[quality["symbol"]] += 1

    profile = profile_cache.get(db, user_id) or {}
    return {
        "user_id": user_id,
        "alias": user.alias,
        "season": current_season,
        "games": per_game,
        "chess": {
            "games": profile.get("games", 0),
            "by_color": profile.get("by_color"),
            "avg_plies": profile.get("avg_plies"),
            "quick_loss_rate": profile.get("quick_loss_rate"),
            "accuracy": profile.get("accuracy"),
            "finish_reasons": finish_reasons,
            "badges": badges,
            "brilliancies": badges.get(BRILLIANT, 0),
        },
    }


def brilliancies(db: Session, user_id: int, limit: int = 30) -> list[dict]:
    """Le mosse col badge 🌟 giocate DALL'UTENTE, dalla più recente.

    Ogni voce porta ciò che serve alla galleria: notazione, avversario, data,
    la semimossa per lo screenshot (``board.png?ply=``) e per aprire la moviola
    sulla posizione esatta.
    """
    out: list[dict] = []
    for s in reversed(_user_sessions(db, user_id, CHESS_CODE)):
        mark = "X" if s.x_user_id == user_id else "O"
        for move in json.loads(s.moves_json or "[]"):
            quality = move.get("quality")
            if not quality or quality.get("symbol") != BRILLIANT:
                continue
            if move.get("player") != mark:
                continue
            out.append(
                {
                    "session_id": s.id,
                    "ply": move.get("ply"),
                    "notation": move.get("notation"),
                    "uci": move.get("id"),
                    "label": quality.get("label"),
                    "opponent": _opponent_label(s, user_id),
                    "game_name": s.game.name,
                    "date": (s.updated_at or s.created_at).isoformat()
                    if (s.updated_at or s.created_at)
                    else None,
                    "result": _result_for(s, user_id),
                }
            )
            if len(out) >= limit:
                return out
    return out
