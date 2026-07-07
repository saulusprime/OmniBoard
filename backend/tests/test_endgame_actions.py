"""Test di abbandono (FIDE 5.1.2) e patta d'accordo (FIDE 9.1)."""

from app.main import app
from fastapi.testclient import TestClient

TOKEN = "test-admin"  # impostato in conftest tramite ADMIN_TOKEN


def _humans(client, tag):
    users = []
    for side in ("a", "b"):
        users.append(
            client.post(
                "/users",
                json={
                    "first_name": "P",
                    "last_name": "R",
                    "alias": f"end_{tag}{side}",
                    "email": f"end_{tag}{side}@e.it",
                    "password": "segretissima1",
                },
            ).json()
        )
    return users


def _session(client, u1, u2, **extra):
    return client.post(
        "/sessions",
        json={
            "game_code": "chess",
            "x": {"type": "human", "user_id": u1["id"]},
            "o": {"type": "human", "user_id": u2["id"]},
            **extra,
        },
    ).json()


def test_resign_gives_win_to_opponent():
    with TestClient(app) as client:
        u1, u2 = _humans(client, "r")
        sid = _session(client, u1, u2)["id"]
        out = client.post(f"/sessions/{sid}/resign", json={"side": "x"}).json()
        assert out["status"] == "finished"
        assert out["winner"] == "o" and out["finish_reason"] == "resign"
        # Partita chiusa: né mosse né un secondo abbandono.
        assert client.post(f"/sessions/{sid}/move", json={"move": "e2e4"}).status_code == 409
        assert client.post(f"/sessions/{sid}/resign", json={"side": "o"}).status_code == 409
        # Lato IA o lato inesistente: rifiutati.
        vs_ai = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": u1["id"]},
                "o": {"type": "ai"},
            },
        ).json()["id"]
        assert client.post(f"/sessions/{vs_ai}/resign", json={"side": "o"}).status_code == 400
        assert client.post(f"/sessions/{vs_ai}/resign", json={"side": "z"}).status_code == 400


def test_draw_agreement_flow():
    with TestClient(app) as client:
        u1, u2 = _humans(client, "d")
        sid = _session(client, u1, u2)["id"]
        # Accettare senza offerta: 409. Offerta di X: resta pendente in vista.
        assert (
            client.post(f"/sessions/{sid}/draw", json={"side": "o", "action": "accept"}).status_code
            == 409
        )
        out = client.post(f"/sessions/{sid}/draw", json={"side": "x", "action": "offer"}).json()
        assert out["draw_offer"] == "x"
        # Doppia offerta dello stesso lato: 409; rifiuto dell'avversario: si azzera.
        assert (
            client.post(f"/sessions/{sid}/draw", json={"side": "x", "action": "offer"}).status_code
            == 409
        )
        out = client.post(f"/sessions/{sid}/draw", json={"side": "o", "action": "decline"}).json()
        assert out["draw_offer"] is None
        # Nuova offerta di X; la MOSSA di O vale come rifiuto (FIDE 9.1).
        client.post(f"/sessions/{sid}/draw", json={"side": "x", "action": "offer"})
        client.post(f"/sessions/{sid}/move", json={"move": "e2e4"})  # muove X (tratto suo)
        after = client.post(f"/sessions/{sid}/move", json={"move": "e7e5"})  # muove O
        assert after.json()["draw_offer"] is None
        # Offerta e ACCETTAZIONE → patta d'accordo.
        client.post(f"/sessions/{sid}/draw", json={"side": "o", "action": "offer"})
        out = client.post(f"/sessions/{sid}/draw", json={"side": "x", "action": "accept"}).json()
        assert out["status"] == "finished"
        assert out["winner"] == "draw" and out["finish_reason"] == "agreement"


def test_draw_vs_ai_rejected_and_remote_needs_token():
    with TestClient(app) as client:
        u1, u2 = _humans(client, "t")
        vs_ai = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": u1["id"]},
                "o": {"type": "ai"},
            },
        ).json()["id"]
        assert (
            client.post(
                f"/sessions/{vs_ai}/draw", json={"side": "x", "action": "offer"}
            ).status_code
            == 409
        )  # l'IA non tratta

        # Partita a distanza: serve il token del PROPRIO lato.
        for u in (u1, u2):
            client.post(f"/users/{u['id']}/approve", headers={"X-Admin-Token": TOKEN})
        t1 = client.post(
            "/auth/login", json={"identifier": u1["alias"], "password": "segretissima1"}
        ).json()["token"]
        sid = _session(client, u1, u2, remote=True)["id"]
        assert client.post(f"/sessions/{sid}/resign", json={"side": "x"}).status_code == 401
        assert (
            client.post(
                f"/sessions/{sid}/resign", json={"side": "o"}, headers={"X-Auth-Token": t1}
            ).status_code
            == 403
        )  # token di u1, lato di u2
        out = client.post(
            f"/sessions/{sid}/resign", json={"side": "x"}, headers={"X-Auth-Token": t1}
        ).json()
        assert out["winner"] == "o" and out["finish_reason"] == "resign"
