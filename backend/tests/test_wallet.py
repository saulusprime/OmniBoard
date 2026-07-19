"""Test della valuta virtuale («gettoni»): premi, idempotenza, estratto conto."""

from app.main import app
from fastapi.testclient import TestClient

TOKEN = "test-admin"


def _login(client, alias):
    client.post(
        "/users",
        json={
            "first_name": "W",
            "last_name": "T",
            "alias": alias,
            "email": f"{alias}@e.it",
            "password": "segretissima1",
        },
    )
    out = client.post("/auth/login", json={"identifier": alias, "password": "segretissima1"})
    if out.status_code != 200:
        users = client.get("/users").json()
        uid = next(u["id"] for u in users if u["alias"] == alias)
        client.post(f"/users/{uid}/approve", headers={"X-Admin-Token": TOKEN})
        out = client.post("/auth/login", json={"identifier": alias, "password": "segretissima1"})
    data = out.json()
    return data["user"]["id"], data["token"]


def test_game_awards_coins_and_wallet_statement():
    with TestClient(app) as client:
        a = _login(client, "coin_a")
        b = _login(client, "coin_b")
        session = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": a[0]},
                "o": {"type": "human", "user_id": b[0]},
            },
        ).json()
        for move in [0, 3, 1, 4, 2]:  # X vince in 5 semimosse (>= coins.min_plies)
            client.post(f"/sessions/{session['id']}/move", json={"move": str(move)})

        me = client.get(f"/users/{a[0]}").json()
        assert me["coins"] == 10  # coins.win
        loser = client.get(f"/users/{b[0]}").json()
        assert loser["coins"] == 2  # coins.loss (partecipazione)

        wallet = client.get(f"/users/{a[0]}/wallet", headers={"X-Auth-Token": a[1]}).json()
        assert wallet["balance"] == 10
        assert wallet["transactions"][0]["amount"] == 10
        assert wallet["transactions"][0]["text"]  # causale leggibile

        # Il portafoglio è personale: col token di un altro → 403.
        resp = client.get(f"/users/{a[0]}/wallet", headers={"X-Auth-Token": b[1]})
        assert resp.status_code == 403


def test_short_game_awards_nothing():
    """Sotto coins.min_plies (abbandono immediato) non si guadagna nulla."""
    with TestClient(app) as client:
        a = _login(client, "coin_short_a")
        b = _login(client, "coin_short_b")
        session = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": a[0]},
                "o": {"type": "human", "user_id": b[0]},
            },
        ).json()
        client.post(f"/sessions/{session['id']}/resign", headers={"X-Auth-Token": a[1]})
        assert client.get(f"/users/{a[0]}").json()["coins"] == 0
        assert client.get(f"/users/{b[0]}").json()["coins"] == 0


def test_draw_awards_both_sides():
    with TestClient(app) as client:
        a = _login(client, "coin_draw_a")
        b = _login(client, "coin_draw_b")
        session = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": a[0]},
                "o": {"type": "human", "user_id": b[0]},
            },
        ).json()
        for move in [0, 1, 2, 4, 3, 5, 7, 6, 8]:  # patta a griglia piena
            client.post(f"/sessions/{session['id']}/move", json={"move": str(move)})
        assert client.get(f"/users/{a[0]}").json()["coins"] == 5  # coins.draw
        assert client.get(f"/users/{b[0]}").json()["coins"] == 5


def test_award_is_idempotent_per_event():
    """Stessa causale + stesso riferimento = un solo accredito."""
    from app import wallet
    from app.database import SessionLocal

    with TestClient(app) as client:
        a = _login(client, "coin_idem")
        db = SessionLocal()
        try:
            assert wallet.award(db, a[0], 7, "puzzle_solved", "puzzle:999") is True
            assert wallet.award(db, a[0], 7, "puzzle_solved", "puzzle:999") is False
            db.commit()
            assert wallet.balance(db, a[0]) == 7
        finally:
            db.close()


def test_lesson_completion_awards_once():
    with TestClient(app) as client:
        a = _login(client, "coin_lesson")
        code = client.get("/lessons").json()["lessons"][0]["code"]
        for _ in range(2):  # completarla due volte non raddoppia i gettoni
            client.post(
                f"/lessons/{code}/progress",
                json={"step": 0, "completed": True},
                headers={"X-Auth-Token": a[1]},
            )
        assert client.get(f"/users/{a[0]}").json()["coins"] == 10  # coins.lesson
