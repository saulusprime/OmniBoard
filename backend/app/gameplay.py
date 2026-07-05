"""Svolgimento delle partite: logica condivisa tra gli endpoint e il worker IA.

La mossa dell'IA **non** viene più calcolata dentro la richiesta HTTP: ``schedule_ai``
la affida a un thread in background (al massimo uno per sessione) e il client si
aggiorna facendo polling dello stato. Così una mossa del motore (anche 2s) o un'intera
partita IA-vs-IA non bloccano mai una risposta.

Con il parametro ``ai.async_moves`` disattivato — o con la variabile d'ambiente
``AI_ASYNC=0``, usata nei test — il calcolo torna in linea, sincrono, come in origine.

Nota: lo scheduling è in-process (un solo worker uvicorn). Passando a più processi va
sostituito con una coda di lavoro vera (vedi TODO.md).
"""

from __future__ import annotations

import json
import logging
import os
import threading

from sqlalchemy.orm import Session

from engine import get_game

from . import ai, ai_providers, chess_profile, models, services, settings_service
from .database import SessionLocal

logger = logging.getLogger(__name__)

_running_lock = threading.Lock()
_running: set[int] = set()


# ----- Stato e log mosse -----
def load_state(game, session: models.GameSession):
    return game.deserialize_state(json.loads(session.state_json))


def save_state(game, session: models.GameSession, state) -> None:
    session.state_json = json.dumps(game.serialize_state(state))


def side_is_ai(session: models.GameSession, player: int) -> bool:
    return session.x_is_ai if player == 0 else session.o_is_ai


def record_move(game, state_before, move, player: int, moves: list) -> None:
    moves.append(
        {
            "ply": len(moves) + 1,
            "player": "X" if player == 0 else "O",
            "notation": game.describe_move(state_before, move),
            "id": game.move_id(move),
        }
    )


def history_ids(moves: list) -> list:
    return [m["id"] for m in moves if "id" in m]


def finish_if_terminal(db: Session, game, session: models.GameSession, state) -> None:
    if session.status == "finished" or not game.is_terminal(state):
        return
    winner = game.outcome(state).winner
    session.winner = "draw" if winner is None else ("x" if winner == 0 else "o")
    session.status = "finished"
    services.finalize_session(db, session)
    db.commit()


def opponent_style(db: Session, game, session: models.GameSession):
    """Stile di gioco dell'IA derivato dal profilo dell'avversario umano (solo scacchi).

    Restituisce ``{'aggression':, 'contempt':}`` o ``None`` (gioco neutro) se non c'è un
    avversario umano identificabile o il gioco non ha un profilo dedicato.
    """
    if game.code != chess_profile.CHESS_CODE:
        return None
    if session.x_is_ai and not session.o_is_ai and session.o_user_id:
        opponent_id = session.o_user_id
    elif session.o_is_ai and not session.x_is_ai and session.x_user_id:
        opponent_id = session.x_user_id
    else:
        return None
    profile = chess_profile.build_profile(db, opponent_id)
    return profile["style"] if profile else None


# ----- Avanzamento IA -----
def advance_ai(db: Session, game, session: models.GameSession) -> None:
    """Fa giocare i lati IA finché non tocca a un umano o la partita finisce.

    Commit dopo **ogni** mossa: il client in polling vede la partita avanzare (utile
    soprattutto per le sessioni IA-vs-IA, che avanzano da sole in background).
    """
    state = load_state(game, session)
    moves = json.loads(session.moves_json or "[]")
    provider = ai_providers.get_active_config(db)
    think_ms = settings_service.get(db, "ai.engine_ms")
    if session.x_is_ai and session.o_is_ai:
        # IA-vs-IA: tante mosse consecutive; un budget ridotto tiene la partita fluida.
        think_ms = min(int(think_ms), 300)
    style = opponent_style(db, game, session)  # adatta il gioco al profilo dell'avversario
    while not game.is_terminal(state):
        player = game.current_player(state)
        if not side_is_ai(session, player):
            break
        move, source = ai.choose_move(
            game, state, history_ids(moves), provider, think_ms=think_ms, jitter=15, style=style
        )
        record_move(game, state, move, player, moves)
        state = game.apply(state, move)
        # last_ai_cell è un intero (cella/colonna); per la dama la mossa è un percorso → None.
        session.last_ai_cell = move if isinstance(move, int) else None
        session.last_ai_source = source
        session.moves_json = json.dumps(moves)
        save_state(game, session, state)
        db.commit()
    finish_if_terminal(db, game, session, state)


# ----- Worker in background -----
def async_enabled(db: Session) -> bool:
    env = os.getenv("AI_ASYNC")
    if env is not None:  # override d'ambiente (nei test: 0 → sincrono)
        return env not in ("0", "false", "no", "")
    return bool(settings_service.get(db, "ai.async_moves"))


def is_running(session_id: int) -> bool:
    with _running_lock:
        return session_id in _running


def schedule_ai(db: Session, session: models.GameSession, sync_fallback: bool = True) -> None:
    """Avvia, se serve, il calcolo delle mosse IA per la sessione.

    Idempotente: al massimo un thread per sessione (richiami ripetuti e polling non ne
    creano di doppi). In modalità sincrona esegue subito in linea, ma solo se
    ``sync_fallback`` è vero (i GET di sola lettura lo passano falso).
    """
    if session.status != "in_progress":
        return
    game = get_game(session.game.code)
    state = load_state(game, session)
    if game.is_terminal(state) or not side_is_ai(session, game.current_player(state)):
        return
    if not async_enabled(db):
        if sync_fallback:
            advance_ai(db, game, session)
        return
    with _running_lock:
        if session.id in _running:
            return
        _running.add(session.id)
    threading.Thread(target=_worker, args=(session.id,), daemon=True).start()


def _worker(session_id: int) -> None:
    """Corpo del thread: sessione DB propria, mai eccezioni fuori.

    In caso d'errore la partita resta al turno dell'IA: il successivo GET dello stato
    riprogramma il calcolo (auto-ripristino, vale anche dopo un riavvio del server).
    """
    db = SessionLocal()
    try:
        session = db.get(models.GameSession, session_id)
        if session and session.status == "in_progress":
            advance_ai(db, get_game(session.game.code), session)
    except Exception:  # noqa: BLE001 - il worker non deve abbattere il processo
        logger.exception("Errore del worker IA sulla sessione %s", session_id)
    finally:
        db.close()
        with _running_lock:
            _running.discard(session_id)
