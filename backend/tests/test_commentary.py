"""Test dei badge di qualità della mossa e del flusso del commentatore."""

from app import commentary
from app.commentary import _classify
from app.main import app
from app.opponents import stockfish
from fastapi.testclient import TestClient

TOKEN = "test-admin"  # impostato in conftest tramite ADMIN_TOKEN


def test_classification_table():
    assert _classify(300, is_best=False, capture=False, retreat=False) == ("🤡", "blunder")
    assert _classify(120, is_best=False, capture=False, retreat=False) == ("😬", "errore")
    assert _classify(60, is_best=False, capture=False, retreat=True) == ("🐔", "codarda")
    assert _classify(60, is_best=False, capture=False, retreat=False) == ("🤔", "imprecisa")
    assert _classify(0, is_best=True, capture=False, retreat=False) == ("🌟", "da maestro")
    assert _classify(10, is_best=False, capture=True, retreat=False) == ("⚔️", "aggressiva")
    assert _classify(10, is_best=False, capture=False, retreat=False) == ("👍", "buona")


def _fake_engine(tmp_path):
    fake = tmp_path / "fakefish"
    fake.write_text(
        '#!/bin/sh\nwhile read line; do\n  case "$line" in\n'
        "    uci) echo 'id name Fakefish'; echo 'uciok';;\n"
        "    go*) echo 'info depth 8 score cp 42 pv e2e4'; echo 'bestmove e2e4';;\n"
        "    quit) exit 0;;\n  esac\ndone\n"
    )
    fake.chmod(0o755)
    return str(fake)


def test_move_gets_quality_badge(tmp_path):
    fake = _fake_engine(tmp_path)
    with TestClient(app) as client:
        client.put(
            "/admin/settings",
            json={"values": {"stockfish.path": fake, "stockfish.analysis_ms": "60"}},
            headers={"X-Admin-Token": TOKEN},
        )
        u1 = client.post(
            "/users",
            json={"first_name": "P", "last_name": "R", "alias": "comm_a", "email": "comm_a@e.it"},
        ).json()
        u2 = client.post(
            "/users",
            json={"first_name": "P", "last_name": "R", "alias": "comm_b", "email": "comm_b@e.it"},
        ).json()
        sid = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": u1["id"]},
                "o": {"type": "human", "user_id": u2["id"]},
            },
        ).json()["id"]
        # Il finto motore suggerisce sempre e2e4: giocarla = «da maestro».
        moves = client.post(f"/sessions/{sid}/move", json={"move": "e2e4"}).json()["moves"]
        # Con AI_ASYNC=0 il commento è sincrono: la view successiva ha il badge.
        moves = client.get(f"/sessions/{sid}").json()["moves"]
        q = moves[0].get("quality")
        assert q and q["symbol"] and q["label"]
        assert "comment" not in moves[0]  # nessun provider LLM attivo nei test

        # Interruttore: spento, la mossa successiva resta senza badge.
        client.put(
            "/admin/settings",
            json={"values": {"commentary.enabled": "false"}},
            headers={"X-Admin-Token": TOKEN},
        )
        client.post(f"/sessions/{sid}/move", json={"move": "e7e5"})
        moves = client.get(f"/sessions/{sid}").json()["moves"]
        assert "quality" not in moves[1]
        client.put(
            "/admin/settings",
            json={
                "values": {
                    "commentary.enabled": "true",
                    "stockfish.analysis_ms": "200",
                    "stockfish.path": "",
                }
            },
            headers={"X-Admin-Token": TOKEN},
        )
        commentary._last_eval.clear()
        stockfish.shutdown()
