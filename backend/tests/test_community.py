"""Test di community (presenza online, badge punti) e partite a distanza.

La partita a distanza è il cuore del gioco fra client diversi: ogni mossa umana
deve arrivare col token del giocatore al tratto; l'hotseat resta senza token.
"""

from app.main import app
from fastapi.testclient import TestClient

TOKEN = "test-admin"  # impostato in conftest tramite ADMIN_TOKEN


def _player(client, alias):
    """Registra, approva e logga un giocatore: (user, auth_token)."""
    user = client.post(
        "/users",
        json={
            "first_name": "P",
            "last_name": "R",
            "alias": alias,
            "email": f"{alias}@e.it",
            "password": "segretissima1",
        },
    ).json()
    client.post(f"/users/{user['id']}/approve", headers={"X-Admin-Token": TOKEN})
    out = client.post("/auth/login", json={"identifier": alias, "password": "segretissima1"}).json()
    return user, out["token"]


def test_online_presence_and_points_badge():
    with TestClient(app) as client:
        user, tok = _player(client, "comm_on")
        # Il login stesso rende online; l'heartbeat rinnova la presenza.
        assert client.post("/auth/heartbeat", headers={"X-Auth-Token": tok}).status_code == 204
        online = client.get("/community/online").json()["online"]
        entry = next((u for u in online if u["id"] == user["id"]), None)
        assert entry is not None
        assert entry["universal_points"] == 0  # badge punteggio complessivo
        # Heartbeat senza token: 401 (la presenza è dei soli autenticati).
        assert client.post("/auth/heartbeat").status_code == 401
        # Il logout esplicito toglie subito dalla lista degli online.
        client.post("/auth/logout", headers={"X-Auth-Token": tok})
        online = client.get("/community/online").json()["online"]
        assert all(u["id"] != user["id"] for u in online)


def test_remote_moves_require_the_token_of_the_side_to_move():
    with TestClient(app) as client:
        ux, tx = _player(client, "comm_x")
        uo, to = _player(client, "comm_o")
        session = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": ux["id"]},
                "o": {"type": "human", "user_id": uo["id"]},
                "remote": True,
            },
        ).json()
        assert session["remote"] is True
        sid = session["id"]

        # Tocca a X: senza token 401, col token di O 403, col token di X ok.
        assert client.post(f"/sessions/{sid}/move", json={"move": "0"}).status_code == 401
        assert (
            client.post(
                f"/sessions/{sid}/move", json={"move": "0"}, headers={"X-Auth-Token": to}
            ).status_code
            == 403
        )
        after = client.post(
            f"/sessions/{sid}/move", json={"move": "0"}, headers={"X-Auth-Token": tx}
        )
        assert after.status_code == 200
        # Ora tocca a O: il token di X viene rifiutato, quello di O passa.
        assert (
            client.post(
                f"/sessions/{sid}/move", json={"move": "1"}, headers={"X-Auth-Token": tx}
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/sessions/{sid}/move", json={"move": "1"}, headers={"X-Auth-Token": to}
            ).status_code
            == 200
        )


def test_hotseat_still_works_without_tokens():
    with TestClient(app) as client:
        ux, _ = _player(client, "comm_hx")
        uo, _ = _player(client, "comm_ho")
        session = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": ux["id"]},
                "o": {"type": "human", "user_id": uo["id"]},
            },
        ).json()
        assert session["remote"] is False
        resp = client.post(f"/sessions/{session['id']}/move", json={"move": "0"})
        assert resp.status_code == 200  # comportamento storico invariato


def test_my_games_lists_the_challenge_for_both_players():
    with TestClient(app) as client:
        ux, tx = _player(client, "comm_gx")
        uo, to = _player(client, "comm_go")
        sid = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": ux["id"]},
                "o": {"type": "human", "user_id": uo["id"]},
                "remote": True,
            },
        ).json()["id"]

        # Lo sfidante (X) la vede col proprio turno; lo sfidato (O) la SCOPRE qui.
        mine_x = client.get("/community/my-games", headers={"X-Auth-Token": tx}).json()["games"]
        gx = next(g for g in mine_x if g["session_id"] == sid)
        assert gx["my_side"] == "x" and gx["my_turn"] is True and gx["opponent"] == "comm_go"
        mine_o = client.get("/community/my-games", headers={"X-Auth-Token": to}).json()["games"]
        go = next(g for g in mine_o if g["session_id"] == sid)
        assert go["my_side"] == "o" and go["my_turn"] is False and go["opponent"] == "comm_gx"
        # Senza token la lista è privata.
        assert client.get("/community/my-games").status_code == 401
