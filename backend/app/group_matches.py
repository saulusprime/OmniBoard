"""Sfide GRUPPO-vs-GRUPPO: squadre a tavoliere multiplo.

Il flusso: un manager dello sfidante propone (gioco + numero di tavolieri),
i manager dello sfidato accettano o rifiutano. All'accettazione:

- le **formazioni** si compongono da sole: i migliori ``boards`` membri di
  ciascun gruppo per Elo stagionale (a parità l'alias), tavolo 1 = il più
  forte contro il più forte; i membri in comune ai DUE gruppi restano fuori
  da entrambe le squadre (nessuno gioca contro sé stesso);
- i **colori si alternano**: ai tavoli dispari il primo tratto va allo
  sfidante, ai pari allo sfidato (convenzione dei match a squadre);
- ogni tavolo è una vera ``GameSession`` a distanza (i giocatori la trovano
  in «le mie partite» e vengono notificati).

Punteggio: 1 a vittoria, ½ a patta, per tavolo. Quando TUTTI i tavoli sono
conclusi (hook ``record_result`` da ``finalize_session``) vince il gruppo con
più punti; la parità è un esito legittimo (``winner_group_id`` resta None).
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from engine import get_game

from . import models, rating

MIN_BOARDS = 1
MAX_BOARDS = 8
MANAGER_ROLES = ("founder", "admin")


def is_manager(db: Session, group_id: int, user_id: int) -> bool:
    m = db.query(models.GroupMembership).filter_by(group_id=group_id, user_id=user_id).first()
    return m is not None and m.role in MANAGER_ROLES


def managers_of(db: Session, group_id: int) -> list[int]:
    rows = db.query(models.GroupMembership).filter_by(group_id=group_id).all()
    return [m.user_id for m in rows if m.role in MANAGER_ROLES]


def lineup(db: Session, match: models.GroupMatch, group_id: int) -> list[models.User]:
    """La formazione del gruppo: i migliori per Elo del gioco (poi alias).

    I membri di ENTRAMBI i gruppi sono esclusi (giocherebbero contro sé
    stessi); la lista è lunga al più ``match.boards``.
    """
    other = (
        match.opponent_group_id
        if group_id == match.challenger_group_id
        else match.challenger_group_id
    )
    other_ids = {
        m.user_id for m in db.query(models.GroupMembership).filter_by(group_id=other).all()
    }
    members = [
        m.user
        for m in db.query(models.GroupMembership).filter_by(group_id=group_id).all()
        if m.user_id not in other_ids
    ]
    season = rating.season(db)

    def key(user: models.User):
        r = (
            db.query(models.Rating)
            .filter_by(user_id=user.id, game_id=match.game_id, season=season)
            .first()
        )
        return (-(r.elo if r else 1500), user.alias)

    return sorted(members, key=key)[: match.boards]


def start(db: Session, match: models.GroupMatch) -> None:
    """All'accettazione: formazioni, sessioni per tavolo, notifiche ai giocatori.

    Chi chiama ha già verificato che entrambe le formazioni siano complete.
    """
    from . import gameplay, notifications

    game = get_game(match.game.code)
    challengers = lineup(db, match, match.challenger_group_id)
    opponents = lineup(db, match, match.opponent_group_id)
    match.status = "running"
    for i in range(match.boards):
        board_no = i + 1
        # Colori alternati: tavoli dispari allo sfidante, pari allo sfidato.
        if board_no % 2 == 1:
            x_user, o_user = challengers[i], opponents[i]
        else:
            x_user, o_user = opponents[i], challengers[i]
        state = game.initial_state()
        session = models.GameSession(
            game_id=match.game_id,
            x_user_id=x_user.id,
            o_user_id=o_user.id,
            x_is_ai=False,
            o_is_ai=False,
            remote=True,
            state_json=json.dumps(game.serialize_state(state)),
            moves_json="[]",
            status="in_progress",
        )
        db.add(session)
        db.flush()
        gameplay.resolve_chance(db, game, session)  # giochi col caso: il server tira
        db.add(
            models.GroupMatchBoard(
                match_id=match.id,
                board=board_no,
                x_user_id=x_user.id,
                o_user_id=o_user.id,
                session_id=session.id,
            )
        )
        for uid in (x_user.id, o_user.id):
            notifications.notify(
                db,
                uid,
                "team_game",
                a=match.challenger_group.name,
                b=match.opponent_group.name,
                board=board_no,
                match_id=match.id,
                session_id=session.id,
            )


def points(match: models.GroupMatch) -> tuple[float, float]:
    """Punti (sfidante, sfidato) dai tavoli conclusi: 1 a vittoria, ½ a patta."""
    a = b = 0.0
    for row in match.board_rows:
        if row.result is None:
            continue
        if row.result == "draw":
            a += 0.5
            b += 0.5
            continue
        winner_uid = row.x_user_id if row.result == "x" else row.o_user_id
        # Il tavolo dispari ha lo sfidante in X, il pari in O (colori alternati):
        # l'appartenenza si ricava dal giocatore, non dal colore.
        if row.board % 2 == 1:
            challenger_uid = row.x_user_id
        else:
            challenger_uid = row.o_user_id
        if winner_uid == challenger_uid:
            a += 1.0
        else:
            b += 1.0
    return a, b


def record_result(db: Session, session: models.GameSession) -> None:
    """Hook da ``finalize_session``: esito del tavolo e, se era l'ultimo, verdetto.

    Niente commit qui (transazione del chiamante, come per punti e rating).
    """
    from . import notifications

    row = db.query(models.GroupMatchBoard).filter_by(session_id=session.id).first()
    if row is None or row.result is not None:
        return
    row.result = session.winner
    match = row.match
    if any(b.result is None for b in match.board_rows):
        return
    a, b = points(match)
    match.status = "finished"
    if a > b:
        match.winner_group_id = match.challenger_group_id
    elif b > a:
        match.winner_group_id = match.opponent_group_id
    names = (match.challenger_group.name, match.opponent_group.name)
    players = {r.x_user_id for r in match.board_rows} | {r.o_user_id for r in match.board_rows}
    for uid in players:
        if match.winner_group_id is None:
            notifications.notify(
                db,
                uid,
                "team_finished_draw",
                a=names[0],
                b=names[1],
                score_a=a,
                score_b=b,
                match_id=match.id,
            )
        else:
            win_first = match.winner_group_id == match.challenger_group_id
            notifications.notify(
                db,
                uid,
                "team_finished",
                winner=names[0] if win_first else names[1],
                loser=names[1] if win_first else names[0],
                score_a=max(a, b),
                score_b=min(a, b),
                match_id=match.id,
            )


def record(db: Session, group_id: int) -> dict:
    """Il bilancio delle sfide CONCLUSE di un gruppo: vinte, pareggiate, perse."""
    rows = (
        db.query(models.GroupMatch)
        .filter(
            models.GroupMatch.status == "finished",
            (models.GroupMatch.challenger_group_id == group_id)
            | (models.GroupMatch.opponent_group_id == group_id),
        )
        .all()
    )
    won = drawn = lost = 0
    for m in rows:
        if m.winner_group_id is None:
            drawn += 1
        elif m.winner_group_id == group_id:
            won += 1
        else:
            lost += 1
    return {"matches": len(rows), "won": won, "drawn": drawn, "lost": lost}
