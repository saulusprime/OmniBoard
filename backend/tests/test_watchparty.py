"""Test del watch party: heatmap dei pronostici degli spettatori."""

from app.main import app
from fastapi.testclient import TestClient

TOKEN = "test-admin"


def _login(client, alias):
    client.post(
        "/users",
        json={
            "first_name": "S",
            "last_name": "P",
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


def _remote_session(client, a, b, game="tictactoe"):
    inv = client.post(
        "/challenges",
        json={"game_code": game, "to_user_id": b[0]},
        headers={"X-Auth-Token": a[1]},
    ).json()
    return client.post(f"/challenges/{inv['id']}/accept", headers={"X-Auth-Token": b[1]}).json()[
        "session_id"
    ]


def test_votes_aggregate_move_and_reset_on_new_ply():
    with TestClient(app) as client:
        a = _login(client, "wp_a")
        b = _login(client, "wp_b")
        sid = _remote_session(client, a, b)

        # Due spettatori anonimi pronosticano; uno cambia idea (voto SPOSTATO).
        r = client.post(
            f"/community/watch/{sid}/vote", json={"cell": 4, "ply": 0, "voter": "k1"}
        ).json()
        assert r["accepted"] and r["total"] == 1 and r["cells"] == {"4": 1}
        client.post(f"/community/watch/{sid}/vote", json={"cell": 4, "ply": 0, "voter": "k2"})
        r = client.post(
            f"/community/watch/{sid}/vote", json={"cell": 0, "ply": 0, "voter": "k1"}
        ).json()
        assert r["total"] == 2 and r["cells"] == {"4": 1, "0": 1}

        # Uno spettatore LOGGATO vota col token (chiave utente, non anonima).
        r = client.post(
            f"/community/watch/{sid}/vote",
            json={"cell": 4, "ply": 0},
            headers={"X-Auth-Token": a[1]},
        ).json()
        assert r["total"] == 3 and r["cells"]["4"] == 2

        # La mossa vera azzera i pronostici (posizione nuova)...
        client.post(f"/sessions/{sid}/move", json={"move": "4"}, headers={"X-Auth-Token": a[1]})
        votes = client.get(f"/community/watch/{sid}/votes").json()
        assert votes == {"ply": 1, "total": 0, "cells": {}}
        # ...e un voto rimasto indietro (ply stantia) viene scartato.
        r = client.post(
            f"/community/watch/{sid}/vote", json={"cell": 8, "ply": 0, "voter": "k9"}
        ).json()
        assert r["accepted"] is False and r["total"] == 0


def test_vote_validation_and_hotseat_not_watchable():
    with TestClient(app) as client:
        a = _login(client, "wp_v_a")
        b = _login(client, "wp_v_b")
        sid = _remote_session(client, a, b)
        # Casella fuori dal tavoliere e spettatore anonimo senza chiave: 400.
        assert (
            client.post(
                f"/community/watch/{sid}/vote", json={"cell": 99, "ply": 0, "voter": "k"}
            ).status_code
            == 400
        )
        assert (
            client.post(f"/community/watch/{sid}/vote", json={"cell": 1, "ply": 0}).status_code
            == 400
        )
        # Le hotseat non sono guardabili: niente pronostici.
        hotseat = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": a[0]},
                "o": {"type": "human", "user_id": b[0]},
            },
        ).json()["id"]
        assert (
            client.post(
                f"/community/watch/{hotseat}/vote", json={"cell": 1, "ply": 0, "voter": "k"}
            ).status_code
            == 404
        )
        assert client.get(f"/community/watch/{hotseat}/votes").status_code == 404
