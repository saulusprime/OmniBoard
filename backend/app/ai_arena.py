"""Arena delle IA: classifica Elo dei concorrenti IA e tornei IA-vs-IA.

Un'IDENTITÀ è la configurazione di un lato non umano — ``motore:<livello>``
(motore locale calibrato), ``stockfish:<preset>``, ``ai:<provider>`` (modello
remoto), più i generici ``ai`` (provider attivo) e ``stockfish`` (parametri
globali). Ogni identità ha un **rating Elo per gioco** (partenza 1500, K=32),
aggiornato a ogni partita **IA-vs-IA** conclusa — contro gli umani non c'è un
rating da confrontare, lì restano i punti 3/1/0.

I TORNEI sono gironi all'italiana tra identità: singolo (una partita per coppia,
il primo elencato ha X) o doppio (andata e ritorno a colori invertiti). Le
partite sono **vere sessioni** giocate in sequenza da un thread (sincrone nei
test con ``AI_ASYNC=0``): restano nello storico con moviola, analisi e PGN, e
alimentano la classifica attraverso il normale flusso di fine partita.

Nota di onestà sportiva: se un'identità non può muovere davvero (binario di
Stockfish assente, provider senza token) gioca il RIPIEGO locale — il risultato
vale comunque per l'identità configurata. La colonna ``last_ai_source`` della
sessione dice chi ha giocato davvero.
"""

from __future__ import annotations

import json
import os
import threading

from engine import get_game

from . import ai_providers, models
from .database import SessionLocal
from .opponents import local, stockfish

ELO_K = 32
ELO_START = 1500.0
MAX_PARTICIPANTS = 8

_lock = threading.Lock()
_running_tournaments: set[int] = set()


# ----- Identità -----
def identities() -> list[dict]:
    """Catalogo dei concorrenti IA: [{code, label}], nell'ordine del setup."""
    entries = [{"code": "ai", "label": "IA (provider attivo)"}]
    entries += [
        {"code": f"ai:{p['code']}", "label": f"IA — {p['label']}"}
        for p in ai_providers.PROVIDER_DEFS
    ]
    entries += [
        {"code": f"motore:{code}", "label": f"Motore — {preset['label']}"}
        for code, preset in local.ENGINE_LEVELS.items()
    ]
    entries += [
        {"code": f"stockfish:{code}", "label": f"Stockfish — {preset['label']}"}
        for code, preset in stockfish.PRESETS.items()
    ]
    entries.append({"code": "stockfish", "label": "Stockfish (parametri globali)"})
    return entries


def label_of(code: str) -> str:
    return next((e["label"] for e in identities() if e["code"] == code), code)


def is_known(code: str) -> bool:
    return any(e["code"] == code for e in identities())


def identity_of(session: models.GameSession, side: int) -> str | None:
    """Identità del lato (None per gli umani): l'inverso di :func:`side_columns`."""
    is_ai = session.x_is_ai if side == 0 else session.o_is_ai
    if not is_ai:
        return None
    kind = (session.x_ai_kind if side == 0 else session.o_ai_kind) or "ai"
    level = session.x_ai_level if side == 0 else session.o_ai_level
    provider = session.x_ai_provider if side == 0 else session.o_ai_provider
    if kind == "stockfish":
        return f"stockfish:{level}" if level else "stockfish"
    if provider:
        return f"ai:{provider}"
    if level:
        return f"motore:{level}"
    return "ai"


def side_columns(code: str) -> dict:
    """Colonne di sessione (kind/level/provider) per un'identità del catalogo."""
    if code == "stockfish":
        return {"kind": "stockfish", "level": None, "provider": None}
    if code == "ai":
        return {"kind": "ai", "level": None, "provider": None}
    prefix, _, value = code.partition(":")
    if prefix == "stockfish":
        return {"kind": "stockfish", "level": value, "provider": None}
    if prefix == "motore":
        return {"kind": "ai", "level": value, "provider": None}
    return {"kind": "ai", "level": None, "provider": value}


# ----- Rating Elo -----
def _rating(db, game_id: int, identity: str) -> models.AiRating:
    row = db.query(models.AiRating).filter_by(game_id=game_id, identity=identity).first()
    if row is None:
        row = models.AiRating(game_id=game_id, identity=identity, elo=ELO_START)
        db.add(row)
        db.flush()
    return row


def _expected(ra: float, rb: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))


def record_result(db, session: models.GameSession) -> None:
    """Aggiorna la classifica delle IA a partita IA-vs-IA conclusa.

    Chiamata da ``services.finalize_session`` (il punto unico di fine partita:
    scacchiera, abbandono, tempo, ripetizione). Le partite con un umano non
    toccano l'Elo delle IA.
    """
    if not (session.x_is_ai and session.o_is_ai) or session.winner is None:
        return
    x_id, o_id = identity_of(session, 0), identity_of(session, 1)
    if not x_id or not o_id or x_id == o_id:
        return  # stessa identità su entrambi i lati: nessuna informazione
    rx, ro = _rating(db, session.game_id, x_id), _rating(db, session.game_id, o_id)
    sx = {"x": 1.0, "o": 0.0, "draw": 0.5}[session.winner]
    ex = _expected(rx.elo, ro.elo)  # dalle valutazioni PRIMA della partita
    rx.elo += ELO_K * (sx - ex)
    ro.elo += ELO_K * ((1.0 - sx) - (1.0 - ex))
    if session.winner == "x":
        rx.wins += 1
        ro.losses += 1
    elif session.winner == "o":
        ro.wins += 1
        rx.losses += 1
    else:
        rx.draws += 1
        ro.draws += 1


def ranking(db, game_id: int) -> list[dict]:
    rows = (
        db.query(models.AiRating)
        .filter_by(game_id=game_id)
        .order_by(models.AiRating.elo.desc())
        .all()
    )
    return [
        {
            "identity": r.identity,
            "label": label_of(r.identity),
            "elo": round(r.elo),
            "wins": r.wins,
            "draws": r.draws,
            "losses": r.losses,
            "games": r.wins + r.draws + r.losses,
        }
        for r in rows
    ]


# ----- Tornei -----
def build_pairings(participants: list[str], double_round: bool) -> list[tuple[str, str]]:
    """Girone all'italiana: ogni coppia una volta (X al primo elencato); col
    doppio girone anche il ritorno a colori invertiti."""
    pairs = []
    for i, a in enumerate(participants):
        for b in participants[i + 1 :]:
            pairs.append((a, b))
            if double_round:
                pairs.append((b, a))
    return pairs


def start(tournament_id: int) -> None:
    """Avvia l'esecuzione del torneo (thread; sincrona nei test con AI_ASYNC=0)."""
    with _lock:
        if tournament_id in _running_tournaments:
            return
        _running_tournaments.add(tournament_id)
    if os.getenv("AI_ASYNC", "1") == "0":
        _run(tournament_id)
    else:
        threading.Thread(target=_run, args=(tournament_id,), daemon=True).start()


def _play_game(db, tournament: models.Tournament, tg: models.TournamentGame) -> None:
    """Gioca UNA partita di torneo come vera sessione (sequenziale, nel runner)."""
    from . import gameplay  # import locale: gameplay importa services → ai_arena

    game = get_game(tournament.game.code)
    x_cols, o_cols = side_columns(tg.x_identity), side_columns(tg.o_identity)
    state = game.initial_state()
    session = models.GameSession(
        game_id=tournament.game_id,
        x_is_ai=True,
        o_is_ai=True,
        x_ai_kind=x_cols["kind"],
        o_ai_kind=o_cols["kind"],
        x_ai_level=x_cols["level"],
        o_ai_level=o_cols["level"],
        x_ai_provider=x_cols["provider"],
        o_ai_provider=o_cols["provider"],
        state_json=json.dumps(game.serialize_state(state)),
        moves_json="[]",
        status="in_progress",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    gameplay.resolve_chance(db, game, session)
    # Direttamente nel thread del torneo (NON schedule_ai): le partite si giocano
    # una alla volta — un solo motore al lavoro, progresso leggibile.
    gameplay.advance_ai(db, game, session)
    db.refresh(session)
    tg.session_id = session.id
    tg.result = session.winner
    db.commit()


def _run(tournament_id: int) -> None:
    db = SessionLocal()
    try:
        tournament = db.get(models.Tournament, tournament_id)
        if tournament is None:
            return
        for tg in sorted(tournament.games, key=lambda g: g.id):
            if tg.result is not None:
                continue  # già giocata (ripresa dopo un riavvio)
            try:
                _play_game(db, tournament, tg)
            except Exception:  # noqa: BLE001 - una partita rotta non ferma il girone
                db.rollback()
        tournament.status = "finished"
        db.commit()
    finally:
        db.close()
        with _lock:
            _running_tournaments.discard(tournament_id)


def standings(db, tournament: models.Tournament) -> list[dict]:
    """Classifica del torneo con i punti di piattaforma (scoring.points_*)."""
    from . import settings_service

    p_win = float(settings_service.get(db, "scoring.points_win"))
    p_draw = float(settings_service.get(db, "scoring.points_draw"))
    p_loss = float(settings_service.get(db, "scoring.points_loss"))
    table: dict[str, dict] = {}

    def row(identity: str) -> dict:
        return table.setdefault(
            identity,
            {
                "identity": identity,
                "label": label_of(identity),
                "points": 0.0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "games": 0,
            },
        )

    for tg in tournament.games:
        rx, ro = row(tg.x_identity), row(tg.o_identity)
        if tg.result is None:
            continue
        rx["games"] += 1
        ro["games"] += 1
        if tg.result == "x":
            rx["wins"] += 1
            rx["points"] += p_win
            ro["losses"] += 1
            ro["points"] += p_loss
        elif tg.result == "o":
            ro["wins"] += 1
            ro["points"] += p_win
            rx["losses"] += 1
            rx["points"] += p_loss
        else:
            rx["draws"] += 1
            ro["draws"] += 1
            rx["points"] += p_draw
            ro["points"] += p_draw
    return sorted(table.values(), key=lambda r: (-r["points"], -r["wins"], r["label"]))
