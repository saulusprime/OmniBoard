"""Tornei fra giocatori UMANI: eliminazione diretta e girone all'italiana.

Il ciclo di vita è ``open`` (iscrizioni) → ``running`` (partite) → ``finished``.
Le partite sono vere ``GameSession`` umano-vs-umano: ciascun iscritto le trova
in «le mie partite» (come le sfide a distanza) e le gioca quando vuole — il
torneo avanza da solo via ``record_result`` (hook in ``services.finalize_session``).

Regole dell'**eliminazione diretta**:

- il tabellone è la potenza di due successiva agli iscritti; i posti vuoti sono
  BYE assegnati alle teste di serie migliori (seed dall'Elo stagionale del
  gioco, a parità l'alias);
- gli accoppiamenti seguono l'ordine classico (1 contro l'ultima testa di
  serie, 2 contro la penultima… le prime due si incontrano solo in finale);
- il seed migliore gioca col Bianco (X); in caso di PATTA passa il Nero (O) —
  la convenzione «draw odds» degli spareggi, che compensa il colore.

Il **girone all'italiana** riusa la logica dell'Arena: ogni coppia una volta
(andata e ritorno con ``double_round``), classifica coi punti di piattaforma
(``scoring.points_*``), spareggio per punti → vittorie → alias.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from engine import get_game

from . import models, rating, settings_service

# Tetti degli iscritti (il girone crea n·(n-1)/2 partite: cresce in fretta).
MAX_KNOCKOUT = 16
MAX_ROUND_ROBIN = 8
FORMATS = ("knockout", "round_robin")


def max_players(t: models.HumanTournament) -> int:
    return MAX_KNOCKOUT if t.format == "knockout" else MAX_ROUND_ROBIN


def _bracket_order(size: int) -> list[int]:
    """L'ordine classico dei seed nel tabellone (1 e 2 s'incontrano in finale)."""
    order = [1]
    while len(order) < size:
        n = len(order) * 2
        order = [s for seed in order for s in (seed, n + 1 - seed)]
    return order


def _assign_seeds(db: Session, t: models.HumanTournament) -> list[models.HumanTournamentPlayer]:
    """Seed dall'Elo stagionale del gioco (1500 se assente), a parità l'alias."""
    season = rating.season(db)

    def key(p: models.HumanTournamentPlayer):
        r = (
            db.query(models.Rating)
            .filter_by(user_id=p.user_id, game_id=t.game_id, season=season)
            .first()
        )
        return (-(r.elo if r else 1500), p.user.alias)

    players = sorted(t.players, key=key)
    for i, p in enumerate(players, start=1):
        p.seed = i
    return players


def _new_session(db: Session, t: models.HumanTournament, x_uid: int, o_uid: int) -> int:
    """Crea la GameSession del torneo (i giocatori la trovano in «le mie partite»)."""
    from . import gameplay  # import locale: gameplay importa services → qui

    game = get_game(t.game.code)
    state = game.initial_state()
    session = models.GameSession(
        game_id=t.game_id,
        x_user_id=x_uid,
        o_user_id=o_uid,
        x_is_ai=False,
        o_is_ai=False,
        state_json=json.dumps(game.serialize_state(state)),
        moves_json="[]",
        status="in_progress",
    )
    db.add(session)
    db.flush()
    gameplay.resolve_chance(db, game, session)  # giochi col caso: il server tira
    return session.id


def start(db: Session, t: models.HumanTournament) -> None:
    """Assegna i seed e crea le partite del primo turno (o TUTTE, nel girone)."""
    players = _assign_seeds(db, t)
    t.status = "running"
    if t.format == "round_robin":
        slot = 0
        for i, a in enumerate(players):
            for b in players[i + 1 :]:
                pairs = [(a, b)] + ([(b, a)] if t.double_round else [])
                for pa, pb in pairs:
                    db.add(
                        models.HumanTournamentGame(
                            tournament_id=t.id,
                            round=1,
                            slot=slot,
                            x_user_id=pa.user_id,
                            o_user_id=pb.user_id,
                            session_id=_new_session(db, t, pa.user_id, pb.user_id),
                        )
                    )
                    slot += 1
        db.commit()
        return

    size = 2
    while size < len(players):
        size *= 2
    by_seed = {p.seed: p for p in players}
    order = _bracket_order(size)
    for slot in range(size // 2):
        a = by_seed.get(order[slot * 2])  # il seed migliore della coppia
        b = by_seed.get(order[slot * 2 + 1])  # può mancare: BYE
        game_row = models.HumanTournamentGame(
            tournament_id=t.id,
            round=1,
            slot=slot,
            x_user_id=a.user_id,
            o_user_id=b.user_id if b else None,
            result=None if b else "x",  # bye: passa subito, nessuna sessione
        )
        if b:
            game_row.session_id = _new_session(db, t, a.user_id, b.user_id)
        db.add(game_row)
    db.flush()
    # Difensivo (un turno di soli bye non capita: size/2 < iscritti).
    _advance_knockout(db, t)
    db.commit()


def _winner_uid(g: models.HumanTournamentGame) -> int:
    """Chi passa il turno: con la patta passa il NERO (draw odds all'O)."""
    return g.x_user_id if g.result == "x" else (g.o_user_id or g.x_user_id)


def record_result(db: Session, session: models.GameSession) -> None:
    """Hook da ``finalize_session``: scrive l'esito e fa avanzare il torneo.

    Niente commit qui: si aggiunge alla transazione del chiamante (che
    committa subito dopo, come per punti e rating).
    """
    tg = db.query(models.HumanTournamentGame).filter_by(session_id=session.id).first()
    if tg is None or tg.result is not None:
        return
    tg.result = session.winner
    t = tg.tournament
    if t.format == "knockout":
        _advance_knockout(db, t)
    else:
        _maybe_finish_round_robin(db, t)


def _advance_knockout(db: Session, t: models.HumanTournament) -> None:
    """Se il turno corrente è completo, crea il successivo (o chiude il torneo)."""
    if t.status != "running":
        return
    last_round = max(g.round for g in t.games)
    current = sorted((g for g in t.games if g.round == last_round), key=lambda g: g.slot)
    if any(g.result is None for g in current):
        return
    winners = [_winner_uid(g) for g in current]
    if len(winners) == 1:
        t.status = "finished"
        t.winner_user_id = winners[0]
        return
    seed_of = {p.user_id: p.seed or 0 for p in t.players}
    for slot in range(len(winners) // 2):
        a, b = winners[slot * 2], winners[slot * 2 + 1]
        if seed_of.get(b, 0) < seed_of.get(a, 0):
            a, b = b, a  # il seed migliore tiene il Bianco anche nei turni interni
        db.add(
            models.HumanTournamentGame(
                tournament_id=t.id,
                round=last_round + 1,
                slot=slot,
                x_user_id=a,
                o_user_id=b,
                session_id=_new_session(db, t, a, b),
            )
        )


def _maybe_finish_round_robin(db: Session, t: models.HumanTournament) -> None:
    if any(g.result is None for g in t.games):
        return
    table = standings(db, t)
    t.status = "finished"
    t.winner_user_id = table[0]["user_id"] if table else None


def standings(db: Session, t: models.HumanTournament) -> list[dict]:
    """Classifica del girone coi punti di piattaforma (punti → vittorie → alias)."""
    p_win = float(settings_service.get(db, "scoring.points_win"))
    p_draw = float(settings_service.get(db, "scoring.points_draw"))
    p_loss = float(settings_service.get(db, "scoring.points_loss"))
    table: dict[int, dict] = {}

    def row(p: models.HumanTournamentPlayer) -> dict:
        return table.setdefault(
            p.user_id,
            {
                "user_id": p.user_id,
                "alias": p.user.alias,
                "seed": p.seed,
                "points": 0.0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "games": 0,
            },
        )

    players = {p.user_id: p for p in t.players}
    for p in t.players:
        row(p)
    for g in t.games:
        if g.result is None or g.o_user_id is None:
            continue
        rx, ro = row(players[g.x_user_id]), row(players[g.o_user_id])
        rx["games"] += 1
        ro["games"] += 1
        if g.result == "x":
            rx["points"] += p_win
            rx["wins"] += 1
            ro["points"] += p_loss
            ro["losses"] += 1
        elif g.result == "o":
            ro["points"] += p_win
            ro["wins"] += 1
            rx["points"] += p_loss
            rx["losses"] += 1
        else:
            rx["points"] += p_draw
            ro["points"] += p_draw
            rx["draws"] += 1
            ro["draws"] += 1
    return sorted(table.values(), key=lambda r: (-r["points"], -r["wins"], r["alias"]))
