"""Test end-to-end del Backgammon via API: il server tira i dadi, i client muovono.

I tiri sono casuali (estratti dal server), quindi le asserzioni sono strutturali:
presenza del tiro nel log, mosse legali coerenti, avanzamento del turno.
"""

from app.main import app
from fastapi.testclient import TestClient


def _make_user(client, alias):
    resp = client.post(
        "/users",
        json={"first_name": "B", "last_name": "G", "alias": alias, "email": f"{alias}@e.it"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_backgammon_session_rolls_and_moves():
    with TestClient(app) as client:
        x = _make_user(client, "bg_x")
        o = _make_user(client, "bg_o")
        session = client.post(
            "/sessions",
            json={
                "game_code": "backgammon",
                "x": {"type": "human", "user_id": x["id"]},
                "o": {"type": "human", "user_id": o["id"]},
            },
        ).json()
        # Il primo tiro è stato materializzato dal SERVER già alla creazione:
        # il log contiene il tiro e ci sono mosse giocabili per X.
        assert session["game_code"] == "backgammon"
        assert any("🎲" in m["notation"] for m in session["moves"])
        assert session["status_line"].startswith("Dadi da giocare")
        assert len(session["playable_moves"]) > 0
        assert session["current"] == "x"  # dalla posizione iniziale X può sempre muovere

        # X gioca il primo dado disponibile: il log cresce con la notazione a pip.
        first = session["playable_moves"][0]
        after = client.post(f"/sessions/{session['id']}/move", json={"move": first["id"]}).json()
        played = [m for m in after["moves"] if "🎲" not in m["notation"]]
        assert len(played) == 1
        assert "/" in played[0]["notation"]  # es. "13/8"

        # Giocando tutti i dadi di X, il turno passa a O e il SUO tiro è già pronto
        # nella risposta (nessun polling necessario per l'umano successivo).
        data = after
        guard = 0
        while data["status"] == "in_progress" and data["current"] == "x" and guard < 6:
            guard += 1
            move = data["playable_moves"][0]
            data = client.post(f"/sessions/{session['id']}/move", json={"move": move["id"]}).json()
        assert data["current"] == "o"
        assert data["status_line"].startswith("Dadi da giocare")
        rolls = [m for m in data["moves"] if "🎲" in m["notation"]]
        assert len(rolls) >= 2  # il tiro di X e quello di O


def test_backgammon_vs_ai_advances():
    with TestClient(app) as client:
        human = _make_user(client, "bg_ai")
        session = client.post(
            "/sessions",
            json={
                "game_code": "backgammon",
                "x": {"type": "human", "user_id": human["id"]},
                "o": {"type": "ai"},
            },
        ).json()
        sid = session["id"]
        # L'umano gioca l'intero turno; in modalità sincrona la risposta finale
        # contiene già il turno completo dell'IA e il nuovo tiro dell'umano.
        data = session
        guard = 0
        while data["status"] == "in_progress" and data["current"] == "x" and guard < 6:
            guard += 1
            move = data["playable_moves"][0]
            data = client.post(f"/sessions/{sid}/move", json={"move": move["id"]}).json()
        assert data["status"] == "in_progress"
        assert data["current"] == "x"  # il turno è tornato all'umano...
        ai_moves = [m for m in data["moves"] if m["player"] == "O" and "🎲" not in m["notation"]]
        assert len(ai_moves) >= 1  # ...dopo che l'IA ha giocato le sue mosse
        assert len(data["playable_moves"]) > 0  # e i nuovi dadi dell'umano sono pronti
