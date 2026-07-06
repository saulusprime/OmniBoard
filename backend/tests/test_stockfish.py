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


def _fake_engine(tmp_path, bestmove="e2e4", die_after_go=False):
    """Finto motore UCI INTERATTIVO: risponde ai comandi e logga ciò che riceve.

    Il log dei comandi (``cmd.log``) permette di verificare cosa il processo
    persistente ha davvero inviato (diff delle opzioni, ucinewgame, posizioni).
    """
    log = tmp_path / "cmd.log"
    fake = tmp_path / "fakefish"
    exit_after = "exit 7" if die_after_go else ":"
    fake.write_text(
        "#!/bin/sh\n"
        f"LOG='{log}'\n"
        "while read line; do\n"
        '  echo "$line" >> "$LOG"\n'
        '  case "$line" in\n'
        "    uci) echo 'id name Fakefish'; echo 'uciok';;\n"
        f"    go*) echo 'bestmove {bestmove}'; {exit_after};;\n"
        "    quit) exit 0;;\n"
        "  esac\n"
        "done\n"
    )
    fake.chmod(0o755)
    return str(fake), log


@pytest.fixture(autouse=True)
def _fresh_engine():
    """Isolamento: ogni test parte (e finisce) senza processo persistente attivo."""
    stockfish.shutdown()
    yield
    stockfish.shutdown()


def test_uci_bridge_with_fake_engine(tmp_path):
    """Il ponte UCI funziona: posizione via FEN, parsing di ``bestmove``."""
    path, _log = _fake_engine(tmp_path)
    game = get_game("chess")
    move = stockfish.best_move(game, game.initial_state(), [], _cfg(path=path))
    assert game.move_id(move) == "e2e4"


def test_uci_bridge_rejects_illegal_bestmove(tmp_path):
    """Un motore che risponde una mossa non legale viene ignorato (→ ripiego)."""
    path, _log = _fake_engine(tmp_path, bestmove="e2e5")  # non legale dall'inizio
    game = get_game("chess")
    assert stockfish.best_move(game, game.initial_state(), [], _cfg(path=path)) is None


def test_engine_process_persists_between_moves(tmp_path):
    """Due mosse = UN processo: handshake una volta, opzioni solo al cambio."""
    path, log = _fake_engine(tmp_path)
    game = get_game("chess")
    state = game.initial_state()

    move1 = stockfish.best_move(game, state, ["d2d4"], _cfg(path=path, elo=1400))
    pid1 = stockfish._ENGINE.stats()["pid"]
    move2 = stockfish.best_move(game, state, ["d2d4", "d7d5"], _cfg(path=path, elo=1400))
    pid2 = stockfish._ENGINE.stats()["pid"]
    assert move1 is not None and move2 is not None
    assert pid1 == pid2  # stesso processo per entrambe le ricerche
    assert stockfish._ENGINE.stats()["searches"] == 2

    received = log.read_text().splitlines()
    assert received.count("uci") == 1  # handshake una volta sola
    # Continuazione della stessa partita: UN solo ucinewgame (hash calde dopo).
    assert received.count("ucinewgame") == 1
    # Opzioni inviate al primo giro e NON ripetute al secondo (diff vuoto).
    assert received.count("setoption name UCI_Elo value 1400") == 1
    # Cambio di forza (altro preset) → il diff riallinea le opzioni.
    stockfish.best_move(game, state, ["e2e4"], _cfg(path=path, elo=0))
    received = log.read_text().splitlines()
    assert "setoption name UCI_LimitStrength value false" in received


def test_engine_respawns_after_crash(tmp_path):
    """Se il processo muore, la mossa successiva lo rilancia da sola."""
    path, _log = _fake_engine(tmp_path, die_after_go=True)  # muore dopo ogni bestmove
    game = get_game("chess")
    state = game.initial_state()
    assert stockfish.best_move(game, state, [], _cfg(path=path)) is not None
    dying = stockfish._ENGINE._proc
    pid_1 = dying.pid
    dying.wait(timeout=5)  # deterministico: il finto motore è davvero uscito
    assert stockfish.best_move(game, state, [], _cfg(path=path)) is not None  # respawn
    assert stockfish._ENGINE._proc.pid != pid_1  # processo nuovo, rilanciato da solo


def test_engine_respawns_when_path_changes(tmp_path):
    """Un percorso binario diverso (cambio config admin) → nuovo processo."""
    dir_a, dir_b = tmp_path / "a", tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    path_a, _ = _fake_engine(dir_a)
    path_b, _ = _fake_engine(dir_b)
    game = get_game("chess")
    state = game.initial_state()
    stockfish.best_move(game, state, [], _cfg(path=path_a))
    pid_a = stockfish._ENGINE.stats()["pid"]
    stockfish.best_move(game, state, [], _cfg(path=path_b))
    pid_b = stockfish._ENGINE.stats()["pid"]
    assert pid_a != pid_b


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
