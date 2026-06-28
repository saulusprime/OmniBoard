"""Test delle sessioni di gioco giocabili (Tris): umano e IA."""

from app.main import app
from fastapi.testclient import TestClient


def make_user(client, alias):
    resp = client.post(
        "/users",
        json={
            "first_name": "Gioca",
            "last_name": "Tore",
            "alias": alias,
            "email": f"{alias}@example.it",
            "nationality": "IT",
            "region": "Lazio",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_human_vs_human_x_wins_and_scores():
    with TestClient(app) as client:
        x = make_user(client, "sess_x")
        o = make_user(client, "sess_o")
        session = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": x["id"]},
                "o": {"type": "human", "user_id": o["id"]},
            },
        ).json()
        assert session["status"] == "in_progress"
        assert session["current"] == "x"

        sid = session["id"]
        data = session
        for cell in [0, 3, 1, 4, 2]:  # X completa la riga in alto
            data = client.post(f"/sessions/{sid}/move", json={"cell": cell}).json()

        assert data["status"] == "finished"
        assert data["winner"] == "x"

        x_detail = client.get(f"/users/{x['id']}").json()
        x_tris = next(s for s in x_detail["scores"] if s["game_code"] == "tictactoe")
        assert x_tris["wins"] == 1
        assert x_tris["points"] == 3.0

        o_detail = client.get(f"/users/{o['id']}").json()
        o_tris = next(s for s in o_detail["scores"] if s["game_code"] == "tictactoe")
        assert o_tris["losses"] == 1


def test_move_validation():
    with TestClient(app) as client:
        x = make_user(client, "val_x")
        o = make_user(client, "val_o")
        sid = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": x["id"]},
                "o": {"type": "human", "user_id": o["id"]},
            },
        ).json()["id"]

        client.post(f"/sessions/{sid}/move", json={"cell": 0})
        occupied = client.post(f"/sessions/{sid}/move", json={"cell": 0})
        assert occupied.status_code == 400


def test_ai_vs_ai_draws():
    """Senza chiave Qwen entrambe le IA usano il minimax locale: il Tris finisce in patta."""
    with TestClient(app) as client:
        session = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "ai"},
                "o": {"type": "ai"},
            },
        ).json()
        assert session["status"] == "finished"
        assert session["winner"] == "draw"
        assert all(cell is not None for cell in session["board"])


def test_batch_ai_vs_ai():
    """100 partite consecutive IA-vs-IA: con minimax sono tutte patte."""
    with TestClient(app) as client:
        result = client.post(
            "/sessions/batch", json={"game_code": "tictactoe", "count": 100}
        ).json()
        assert result["count"] == 100
        assert result["x_wins"] + result["o_wins"] + result["draws"] == 100
        assert result["draws"] == 100  # gioco perfetto su entrambi i lati


def test_batch_invalid_count():
    with TestClient(app) as client:
        too_low = client.post("/sessions/batch", json={"game_code": "tictactoe", "count": 0})
        assert too_low.status_code == 422
        too_high = client.post("/sessions/batch", json={"game_code": "tictactoe", "count": 1001})
        assert too_high.status_code == 422


def test_human_vs_ai_responds():
    with TestClient(app) as client:
        human = make_user(client, "hva_x")
        session = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": human["id"]},
                "o": {"type": "ai"},
            },
        ).json()
        assert session["current"] == "x"  # l'umano (X) muove per primo

        sid = session["id"]
        after = client.post(f"/sessions/{sid}/move", json={"cell": 4}).json()
        # l'IA (O) deve aver risposto
        assert "O" in after["board"]
        assert after["last_ai"] is not None
        assert after["last_ai"]["source"] in ("qwen", "local")
        if after["status"] != "finished":
            assert after["current"] == "x"
