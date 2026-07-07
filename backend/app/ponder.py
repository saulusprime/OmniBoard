"""Pondering: il motore locale pensa DURANTE il turno dell'umano (solo scacchi).

Mentre l'avversario umano riflette, un thread cerca sulla posizione corrente e
riempie una **transposition table condivisa per sessione**; quando la mossa
umana arriva, la ricerca vera del worker riusa quella TT: molte posizioni sono
già valutate → più profondità nello stesso budget. È la forma di pondering
adatta alla nostra architettura (nessun "ponderhit" da gestire: si pondera la
posizione, non una mossa predetta — qualunque replica umana beneficia dei
sottoalberi già esplorati).

Ciclo di vita: ``start`` quando il turno passa all'umano (fine del worker IA),
``stop`` all'arrivo della sua mossa (o di abbandono/patta), ``drop`` a partita
finita. Attivo solo con: mosse async, partita di scacchi con un solo lato IA di
tipo «ai» (Stockfish ha il suo processo e i provider remoti non ne beneficiano),
e ``ponder.enabled`` acceso. Con ``AI_ASYNC=0`` (test) è un no-op.
"""

from __future__ import annotations

import json
import os
import threading

from engine import get_game

from . import models, settings_service
from .database import SessionLocal
from .gameplay import history_ids, load_state

_PONDER_SECONDS = 60  # una "pensata" massima per turno umano (poi il thread si spegne)
_TT_MAX_ENTRIES = 400_000  # tetto di memoria: oltre, la TT riparte da zero

_lock = threading.Lock()
# {session_id: {"tt": dict condivisa, "stop": Event, "thread": Thread}}
_store: dict[int, dict] = {}


def tt_for(session_id: int) -> dict | None:
    """La TT condivisa della sessione (per la ricerca vera del worker)."""
    with _lock:
        entry = _store.get(session_id)
        return entry["tt"] if entry else None


def active(session_id: int) -> bool:
    with _lock:
        entry = _store.get(session_id)
        return bool(entry and entry["thread"] and entry["thread"].is_alive())


def start(db, session: models.GameSession) -> bool:
    """Avvia il pondering se la sessione lo merita (vedi condizioni nel modulo)."""
    if os.getenv("AI_ASYNC", "1") == "0":
        return False  # sincrono (test): nessun thread di sottofondo
    if session.status != "in_progress" or session.game.code != "chess":
        return False
    if session.x_is_ai == session.o_is_ai:  # 0 o 2 lati IA: nessun turno umano da usare
        return False
    ai_kind = session.x_ai_kind if session.x_is_ai else session.o_ai_kind
    if (ai_kind or "ai") != "ai":
        return False  # Stockfish pondera già col suo processo; qui serve al motore locale
    level = session.x_ai_level if session.x_is_ai else session.o_ai_level
    if level and level != "maestro":
        return False  # un livello depotenziato non deve rinforzarsi con la TT ponderata
    if not settings_service.get(db, "ponder.enabled"):
        return False

    with _lock:
        entry = _store.setdefault(session.id, {"tt": {}, "stop": threading.Event(), "thread": None})
        if entry["thread"] and entry["thread"].is_alive():
            return True  # già in pensiero
        if len(entry["tt"]) > _TT_MAX_ENTRIES:
            entry["tt"].clear()
        entry["stop"] = threading.Event()
        entry["thread"] = threading.Thread(
            target=_run, args=(session.id, entry["tt"], entry["stop"]), daemon=True
        )
        entry["thread"].start()
    return True


def _run(session_id: int, tt: dict, stop: threading.Event) -> None:
    db = SessionLocal()
    try:
        session = db.get(models.GameSession, session_id)
        if session is None or session.status != "in_progress":
            return
        game = get_game(session.game.code)
        state = load_state(game, session)
        history = history_ids(json.loads(session.moves_json or "[]"))
        # La pensata riempie la TT; la mossa restituita non interessa (jitter 0,
        # niente stile: contano i sottoalberi, non la scelta).
        game.engine_move(
            state,
            history=history,
            time_limit=_PONDER_SECONDS,
            tt=tt,
            stop=stop,
        )
    except Exception:  # noqa: BLE001 - il pondering non deve mai disturbare la partita
        pass
    finally:
        db.close()


def stop(session_id: int) -> None:
    """Interrompe la pensata (l'umano ha mosso): la TT resta per la ricerca vera."""
    with _lock:
        entry = _store.get(session_id)
    if not entry:
        return
    entry["stop"].set()
    thread = entry["thread"]
    if thread and thread.is_alive():
        thread.join(timeout=1.0)


def drop(session_id: int) -> None:
    """Partita finita: ferma tutto e libera la memoria della sessione."""
    stop(session_id)
    with _lock:
        _store.pop(session_id, None)
