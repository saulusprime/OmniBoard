"""Logica di assegnazione dei punteggi, condivisa da partite e sessioni di gioco.

I punti assegnati sono parametri configurabili dal super admin
(``scoring.points_win`` / ``points_draw`` / ``points_loss``).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from . import models, settings_service


def score_for(db: Session, user_id: int, game_id: int) -> models.Score:
    """Recupera (o crea, con valori a zero) il punteggio di un utente per un gioco."""
    score = db.query(models.Score).filter_by(user_id=user_id, game_id=game_id).first()
    if not score:
        score = models.Score(
            user_id=user_id,
            game_id=game_id,
            points=0.0,
            matches_played=0,
            wins=0,
            draws=0,
            losses=0,
        )
        db.add(score)
    return score


def award(db: Session, user_id: int, game_id: int, result: str) -> models.Score:
    """Aggiorna il punteggio di un utente. ``result`` ∈ {"win", "draw", "loss"}."""
    score = score_for(db, user_id, game_id)
    score.matches_played += 1
    if result == "win":
        score.points += settings_service.get(db, "scoring.points_win")
        score.wins += 1
    elif result == "draw":
        score.points += settings_service.get(db, "scoring.points_draw")
        score.draws += 1
    else:
        score.points += settings_service.get(db, "scoring.points_loss")
        score.losses += 1
    return score


def finalize_session(db: Session, session: "models.GameSession") -> None:
    """Assegna i punti alla fine di una sessione (solo ai giocatori umani).

    ``session.winner`` ∈ {"x", "o", "draw"}.
    """
    gid = session.game_id
    x_uid, o_uid = session.x_user_id, session.o_user_id

    if session.winner == "draw":
        if x_uid:
            award(db, x_uid, gid, "draw")
        if o_uid:
            award(db, o_uid, gid, "draw")
    elif session.winner == "x":
        if x_uid:
            award(db, x_uid, gid, "win")
        if o_uid:
            award(db, o_uid, gid, "loss")
    elif session.winner == "o":
        if o_uid:
            award(db, o_uid, gid, "win")
        if x_uid:
            award(db, x_uid, gid, "loss")
