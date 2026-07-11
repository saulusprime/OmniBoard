"""Test end-to-end dei giochi nuovi (Othello e Gomoku) sulla piattaforma."""

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


def test_catalog_lists_new_games():
    with TestClient(app) as client:
        games = {g["code"]: g for g in client.get("/games").json()}
        assert games["othello"]["name"] == "Othello"
        assert games["gomoku"]["name"] == "Gomoku"
        assert not games["othello"]["is_stochastic"]


def test_othello_session_flow_and_ai_reply():
    with TestClient(app) as client:
        human = make_user(client, "oth_h")
        session = client.post(
            "/sessions",
            json={
                "game_code": "othello",
                "x": {"type": "human", "user_id": human["id"]},
                "o": {"type": "ai"},
            },
        ).json()
        assert session["move_type"] == "cell"
        assert session["rows"] == 8 and session["cols"] == 8
        assert sorted(session["legal_moves"]) == [19, 26, 37, 44]
        assert session["board"][28] == "●" and session["board"][27] == "○"
        assert session["status_line"] == "● 2 — ○ 2"

        after = client.post(f"/sessions/{session['id']}/move", json={"move": "19"}).json()
        assert after["board"][19] == "●"  # la posa del Nero resta (nessun giro può toccarla)
        # L'IA (Bianco) ha risposto: c'è almeno una ○ e il log conta due mosse.
        assert any(v == "○" for v in after["board"])
        assert len(after["moves"]) == 2
        assert after["last_ai"]["source"] in ("qwen", "local")


def test_othello_illegal_cell_is_rejected():
    with TestClient(app) as client:
        x = make_user(client, "oth_x2")
        o = make_user(client, "oth_o2")
        session = client.post(
            "/sessions",
            json={
                "game_code": "othello",
                "x": {"type": "human", "user_id": x["id"]},
                "o": {"type": "human", "user_id": o["id"]},
            },
        ).json()
        resp = client.post(f"/sessions/{session['id']}/move", json={"move": "0"})
        assert resp.status_code == 400


def test_gomoku_session_flow_human_win():
    with TestClient(app) as client:
        x = make_user(client, "gmk_x")
        o = make_user(client, "gmk_o")
        session = client.post(
            "/sessions",
            json={
                "game_code": "gomoku",
                "x": {"type": "human", "user_id": x["id"]},
                "o": {"type": "human", "user_id": o["id"]},
            },
        ).json()
        assert session["rows"] == 15 and session["cols"] == 15
        sid = session["id"]
        data = session
        for move in [112, 0, 113, 1, 114, 2, 115, 3, 116]:  # cinquina del Nero
            data = client.post(f"/sessions/{sid}/move", json={"move": str(move)}).json()
        assert data["status"] == "finished"
        assert data["winner"] == "x"
        assert data["moves"][-1]["notation"] == "l8"


def test_gomoku_vs_ai_responds_with_engine():
    with TestClient(app) as client:
        human = make_user(client, "gmk_ai")
        session = client.post(
            "/sessions",
            json={
                "game_code": "gomoku",
                "x": {"type": "human", "user_id": human["id"]},
                "o": {"type": "ai"},
            },
        ).json()
        after = client.post(f"/sessions/{session['id']}/move", json={"move": "112"}).json()
        assert any(v == "○" for v in after["board"])  # l'IA ha risposto
        # Senza provider configurato risponde il motore dedicato del Gomoku.
        assert after["last_ai"]["source"] in ("qwen", "engine")
