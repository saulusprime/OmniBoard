"""Test del pondering: TT condivisa, stop esterno, ciclo di vita per sessione."""

import threading
import time

from app import ponder
from app.database import SessionLocal
from app.main import app
from fastapi.testclient import TestClient

from engine import get_game
from engine.chess.context import SearchContext
from engine.chess.engine import _search_root, best_move


def test_shared_tt_reduces_work():
    """La seconda ricerca sulla stessa posizione, con la TT della prima, costa meno."""
    game = get_game("chess")
    state = game.initial_state()
    shared: dict = {}

    def run():
        ctx = SearchContext(game=game, deadline=time.monotonic() + 600, jitter=0)
        ctx.tt = shared
        ctx.root_side = state.current
        best = None
        for d in range(1, 6):
            _score, best = _search_root(ctx, state, d, best)
        return ctx.nodes

    fresh = run()
    warmed = run()  # stessa TT: gran parte dell'albero è già valutato
    assert warmed < fresh / 3


def test_stop_event_aborts_search():
    game = get_game("chess")
    stop = threading.Event()
    stop.set()  # stop già richiesto: la ricerca deve uscire subito dopo depth 1
    t0 = time.monotonic()
    move = best_move(game, game.initial_state(), time_limit=30, jitter=0, stop=stop)
    assert move is not None  # la profondità 1 si completa sempre: mossa legale
    assert time.monotonic() - t0 < 2.0


def test_ponder_lifecycle(monkeypatch):
    from types import SimpleNamespace

    # Le CONDIZIONI di avvio si provano su un finto oggetto-sessione (creare una
    # partita IA-vs-IA sincrona giocherebbe l'intera partita nel test).
    fake_ai_vs_ai = SimpleNamespace(
        id=999999,
        status="in_progress",
        game=SimpleNamespace(code="chess"),
        x_is_ai=True,
        o_is_ai=True,
        x_ai_kind="ai",
        o_ai_kind="ai",
    )
    # Con AI_ASYNC=0 (default dei test) il pondering è un no-op.
    assert ponder.start(None, fake_ai_vs_ai) is False
    monkeypatch.setenv("AI_ASYNC", "1")
    fake_stockfish = SimpleNamespace(
        id=999998,
        status="in_progress",
        game=SimpleNamespace(code="chess"),
        x_is_ai=False,
        o_is_ai=True,
        x_ai_kind=None,
        o_ai_kind="stockfish",
    )
    with TestClient(app) as client:
        db = SessionLocal()
        try:
            # IA-vs-IA (nessun turno umano) e lato Stockfish: esclusi.
            assert ponder.start(db, fake_ai_vs_ai) is False
            assert ponder.start(db, fake_stockfish) is False
        finally:
            db.close()
        monkeypatch.setenv("AI_ASYNC", "0")

        # Umano vs IA: il pondering parte, si ferma e si ripulisce.
        u = client.post(
            "/users",
            json={
                "first_name": "P",
                "last_name": "R",
                "alias": "ponder_u",
                "email": "ponder_u@e.it",
            },
        ).json()
        monkeypatch.setenv("AI_ASYNC", "0")  # creazione sessione in modalità sincrona
        sid2 = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": u["id"]},
                "o": {"type": "ai"},
            },
        ).json()["id"]
        db = SessionLocal()
        try:
            from app.models import GameSession

            session2 = db.get(GameSession, sid2)
            monkeypatch.setenv("AI_ASYNC", "1")
            assert ponder.start(db, session2) is True
            assert ponder.active(sid2) is True
            assert isinstance(ponder.tt_for(sid2), dict)
            ponder.stop(sid2)
            assert ponder.active(sid2) is False
            assert ponder.tt_for(sid2) is not None  # la TT sopravvive allo stop
            ponder.drop(sid2)
            assert ponder.tt_for(sid2) is None  # a fine partita si libera tutto
        finally:
            db.close()
