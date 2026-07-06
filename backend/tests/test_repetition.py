"""Test della patta per triplice ripetizione (dichiarata a fine mossa dal server)."""

from app.main import app
from fastapi.testclient import TestClient

from engine import get_game

# Giro di cavalli: dopo ogni blocco di 4 semimosse si torna alla posizione iniziale.
SHUFFLE = ["g1f3", "g8f6", "f3g1", "f6g8"]


def test_engine_detects_threefold():
    game = get_game("chess")
    assert game.is_repetition_draw(SHUFFLE) is False  # posizione iniziale: 2 volte
    assert game.is_repetition_draw(SHUFFLE * 2) is True  # terza occorrenza
    # La base comune non dichiara mai (giochi senza la regola).
    assert get_game("tictactoe").is_repetition_draw(["0", "1"]) is False


def test_session_ends_in_repetition_draw():
    with TestClient(app) as client:
        u1 = client.post(
            "/users",
            json={"first_name": "P", "last_name": "R", "alias": "rep_a", "email": "rep_a@e.it"},
        ).json()
        u2 = client.post(
            "/users",
            json={"first_name": "P", "last_name": "R", "alias": "rep_b", "email": "rep_b@e.it"},
        ).json()
        sid = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": u1["id"]},
                "o": {"type": "human", "user_id": u2["id"]},
            },
        ).json()["id"]
        last = None
        for uci in SHUFFLE * 2:
            last = client.post(f"/sessions/{sid}/move", json={"move": uci})
            assert last.status_code == 200, last.text
        final = last.json()
        assert final["status"] == "finished"
        assert final["winner"] == "draw"
        assert final["finish_reason"] == "repetition"
        # Una mossa dopo la fine viene rifiutata (partita già conclusa).
        assert client.post(f"/sessions/{sid}/move", json={"move": "e2e4"}).status_code == 409
