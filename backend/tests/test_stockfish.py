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


def test_presets_are_complete_and_sane():
    """I sei livelli con nomi di divinità greche, dal più forte al più debole."""
    assert list(stockfish.PRESETS) == ["zeus", "atena", "apollo", "ares", "hermes", "pan"]
    expected = ["Extreme", "Master", "Champion", "Expert", "Middle", "Learner"]
    for (key, preset), difficulty in zip(stockfish.PRESETS.items(), expected):
        assert f"({difficulty})" in preset["label"], key
        assert preset["elo"] == 0 or 1320 <= preset["elo"] <= 3190
        assert preset["move_ms"] >= 100
    # Zeus è piena forza; i livelli Elo decrescono strettamente.
    assert stockfish.PRESETS["zeus"]["elo"] == 0
    elos = [p["elo"] for k, p in stockfish.PRESETS.items() if k != "zeus"]
    assert elos == sorted(elos, reverse=True)


def test_config_for_level_merges_preset_over_base():
    base = _cfg(path="/usr/local/bin/stockfish", move_ms=999, elo=0, skill_level=20)
    pan = stockfish.config_for_level(base, "pan")
    assert pan["path"] == base["path"]  # il percorso resta quello globale
    assert pan["elo"] == 1400 and pan["move_ms"] == 500
    # Livello assente o sconosciuto → configurazione globale invariata.
    assert stockfish.config_for_level(base, None) == base
    assert stockfish.config_for_level(base, "boh") == base


def test_session_with_stockfish_level_exposed_and_validated():
    with TestClient(app) as client:
        user = client.post(
            "/users",
            json={"first_name": "L", "last_name": "V", "alias": "lvl", "email": "lvl@e.it"},
        ).json()
        session = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": user["id"]},
                "o": {"type": "stockfish", "level": "pan"},
            },
        ).json()
        assert session["players"]["o"]["level"] == "pan"
        assert session["players"]["o"]["level_label"] == "Pan (Learner)"
        # Livello sconosciuto → 400.
        bad = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": user["id"]},
                "o": {"type": "stockfish", "level": "kraken"},
            },
        )
        assert bad.status_code == 400


def test_verify_reports_missing_binary():
    ok, detail = stockfish.verify(_cfg(path=""))
    assert ok is False and "Nessun binario" in detail
    ok, detail = stockfish.verify(_cfg(path="/percorso/inesistente"))
    assert ok is False and "non trovato" in detail


def test_verify_with_fake_engine(tmp_path):
    fake = tmp_path / "fakefish"
    fake.write_text("#!/bin/sh\necho 'id name Fakefish 1.0'\necho 'uciok'\necho 'bestmove e2e4'\n")
    fake.chmod(0o755)
    ok, detail = stockfish.verify(_cfg(path=str(fake)))
    assert ok is True
    assert "Fakefish 1.0" in detail and "e2e4" in detail


def test_admin_stockfish_test_endpoint(tmp_path, monkeypatch):
    """L'endpoint di verifica richiede il token e riporta esito + percorso risolto."""
    with TestClient(app) as client:
        # Senza token super admin → 401.
        assert client.post("/admin/stockfish/test").status_code == 401
        # Con token ma binario inesistente: ok=false con spiegazione. (Si forza un
        # percorso non valido: sul PATH della macchina potrebbe esserci uno stockfish vero.)
        monkeypatch.setenv("STOCKFISH_PATH", "/percorso/inesistente")
        result = client.post(
            "/admin/stockfish/test", headers={"X-Admin-Token": "test-admin"}
        ).json()
        assert result["ok"] is False
        # Con un finto binario (via STOCKFISH_PATH): ok=true e percorso riportato.
        fake = tmp_path / "fakefish"
        fake.write_text("#!/bin/sh\necho 'id name Fakefish'\necho 'bestmove e2e4'\n")
        fake.chmod(0o755)
        monkeypatch.setenv("STOCKFISH_PATH", str(fake))
        result = client.post(
            "/admin/stockfish/test", headers={"X-Admin-Token": "test-admin"}
        ).json()
        assert result["ok"] is True
        assert result["path"] == str(fake)


@pytest.mark.skipif(shutil.which("stockfish") is None, reason="binario stockfish assente")
def test_real_stockfish_plays_a_legal_move():
    """Se Stockfish è installato davvero, deve produrre una mossa legale."""
    game = get_game("chess")
    state = game.initial_state()
    move = stockfish.best_move(game, state, [], _cfg(path=shutil.which("stockfish"), move_ms=100))
    assert move in game.legal_moves(state)
