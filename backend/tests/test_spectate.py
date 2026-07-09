"""Spettatori: elenco delle partite in diretta e moviola per il replay animato."""

from app.main import app
from fastapi.testclient import TestClient

TOKEN = "test-admin"
FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]


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


def _h(token):
    return {"X-Auth-Token": token}


def test_live_list_only_remote_games_and_replay_frames():
    with TestClient(app) as client:
        a = _login(client, "sp_a")
        b = _login(client, "sp_b")

        # Una partita HOTSEAT in corso: NON è guardabile (chiunque muoverebbe).
        hotseat = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": a[0]},
                "o": {"type": "human", "user_id": b[0]},
            },
        ).json()["id"]

        # Una sfida accettata = partita A DISTANZA: compare fra le dirette.
        inv = client.post(
            "/challenges",
            json={"game_code": "chess", "to_user_id": b[0]},
            headers=_h(a[1]),
        ).json()
        remote_sid = client.post(f"/challenges/{inv['id']}/accept", headers=_h(b[1])).json()[
            "session_id"
        ]

        live = client.get("/community/live").json()["live"]
        ids = {entry["session_id"] for entry in live}
        assert remote_sid in ids and hotseat not in ids
        row = next(entry for entry in live if entry["session_id"] == remote_sid)
        assert row["x_label"] == "sp_a" and row["o_label"] == "sp_b"
        assert row["plies"] == 0 and row["ai_only"] is False

        # A partita finita esce dalle dirette; la moviola ha semimosse+1 posizioni.
        movers = [a, b, a, b]
        for uci, mover in zip(FOOLS_MATE, movers):
            assert (
                client.post(
                    f"/sessions/{remote_sid}/move",
                    json={"move": uci},
                    headers=_h(mover[1]),
                ).status_code
                == 200
            )
        live = client.get("/community/live").json()["live"]
        assert remote_sid not in {entry["session_id"] for entry in live}
        replay = client.get(f"/sessions/{remote_sid}/replay").json()
        assert len(replay["boards"]) == len(FOOLS_MATE) + 1
        assert len(replay["boards"][0]) == 64  # posizione iniziale completa
