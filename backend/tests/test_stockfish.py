"""Test dell'avversario Stockfish (ponte UCI) e del dispatch per tipo di avversario.

Il vero binario di Stockfish può non essere installato: il ponte UCI si testa con un
**finto motore** (script shell che risponde come Stockfish), il resto verifica il
ripiego sul giocatore locale e il flusso end-to-end con tipo "stockfish".
"""

import shutil

import pytest
from app import opponents
from app.main import app
from app.opponents import stockfish
from fastapi.testclient import TestClient

from engine import get_game


def _cfg(path="", move_ms=200, elo=0, skill_level=20):
    return {"path": path, "move_ms": move_ms, "elo": elo, "skill_level": skill_level}


def test_not_available_without_binary():
    assert stockfish.is_available(_cfg(path="")) is False
    assert stockfish.is_available(_cfg(path="/percorso/inesistente")) is False


def test_best_move_none_for_non_chess():
    game = get_game("tictactoe")
    assert stockfish.best_move(game, game.initial_state(), [], _cfg(path="/bin/sh")) is None


def test_uci_bridge_with_fake_engine(tmp_path):
    """Il dialogo UCI one-shot funziona: posizione via FEN, parsing di ``bestmove``."""
    fake = tmp_path / "fakefish"
    fake.write_text("#!/bin/sh\necho 'id name Fakefish'\necho 'uciok'\necho 'bestmove e2e4'\n")
    fake.chmod(0o755)
    game = get_game("chess")
    move = stockfish.best_move(game, game.initial_state(), [], _cfg(path=str(fake)))
    assert game.move_id(move) == "e2e4"


def test_uci_bridge_rejects_illegal_bestmove(tmp_path):
    """Un motore che risponde una mossa non legale viene ignorato (→ ripiego)."""
    fake = tmp_path / "fakefish"
    fake.write_text("#!/bin/sh\necho 'bestmove e2e5'\n")  # e2e5 non è legale dall'inizio
    fake.chmod(0o755)
    game = get_game("chess")
    assert stockfish.best_move(game, game.initial_state(), [], _cfg(path=str(fake))) is None


def test_dispatcher_falls_back_to_local_when_stockfish_missing():
    game = get_game("chess")
    state = game.initial_state()
    move, source = opponents.choose_move(
        game, state, history=None, kind="stockfish", stockfish_cfg=_cfg(path="")
    )
    assert move in game.legal_moves(state)
    assert source in ("engine", "local")  # ha giocato il ripiego locale


def test_session_with_stockfish_side_plays_via_fallback():
    """End-to-end: lato O di tipo "stockfish" (binario assente) → gioca il ripiego."""
    with TestClient(app) as client:
        user = client.post(
            "/users",
            json={"first_name": "S", "last_name": "F", "alias": "vs_sf", "email": "sf@e.it"},
        ).json()
        session = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": user["id"]},
                "o": {"type": "stockfish"},
            },
        ).json()
        assert session["players"]["o"]["type"] == "stockfish"
        after = client.post(f"/sessions/{session['id']}/move", json={"move": "e2e4"}).json()
        assert len(after["moves"]) == 2  # la mossa di risposta c'è comunque (fallback)
        assert after["current"] == "x"


@pytest.mark.skipif(shutil.which("stockfish") is None, reason="binario stockfish assente")
def test_real_stockfish_plays_a_legal_move():
    """Se Stockfish è installato davvero, deve produrre una mossa legale."""
    game = get_game("chess")
    state = game.initial_state()
    move = stockfish.best_move(game, state, [], _cfg(path=shutil.which("stockfish"), move_ms=100))
    assert move in game.legal_moves(state)
