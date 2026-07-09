"""Sfide gruppo-vs-gruppo: formazioni per Elo, colori alternati, verdetto."""

from app.main import app
from fastapi.testclient import TestClient

TOKEN = "test-admin"
FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]  # vince il Nero (O)


def _login(client, alias):
    client.post(
        "/users",
        json={
            "first_name": "G",
            "last_name": "M",
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


def _found_group(client, name, founder, voter):
    prop = client.post(
        "/groups/proposals",
        json={"name": name, "proposed_by": founder[0], "threshold": 2},
    ).json()
    out = client.post(
        f"/groups/proposals/{prop['id']}/vote", json={"user_id": voter[0], "in_favor": True}
    ).json()
    assert out["status"] == "founded"
    return out["group_id"]


def _join_via_invite(client, gid, manager, member):
    inv = client.post(
        f"/groups/{gid}/invites", json={"user_id": member[0]}, headers=_h(manager[1])
    ).json()
    client.post(
        f"/groups/invites/{inv['id']}/respond", json={"accept": True}, headers=_h(member[1])
    )


def _texts(client, token):
    data = client.get("/notifications", headers=_h(token)).json()
    return [n["text"] for n in data["notifications"]]


def test_group_match_full_flow_with_overlap_and_verdict():
    with TestClient(app) as client:
        a = _login(client, "gm_a")  # founder del gruppo Alfieri
        b = _login(client, "gm_b")  # membro Alfieri
        c = _login(client, "gm_c")  # founder del gruppo Torri
        d = _login(client, "gm_d")  # membro Torri
        e = _login(client, "gm_e")  # membro di ENTRAMBI: escluso dalle formazioni
        ga = _found_group(client, "Alfieri", a, b)
        gb = _found_group(client, "Torri", c, d)
        _join_via_invite(client, ga, a, e)
        _join_via_invite(client, gb, c, e)

        # Propone solo un manager dello sfidante; validazioni su gruppi e tavolieri.
        payload = {
            "game_code": "chess",
            "challenger_group_id": ga,
            "opponent_group_id": gb,
            "boards": 2,
        }
        assert client.post("/group-matches", json=payload).status_code == 401
        assert client.post("/group-matches", json=payload, headers=_h(b[1])).status_code == 403
        assert (
            client.post(
                "/group-matches",
                json={**payload, "opponent_group_id": ga},
                headers=_h(a[1]),
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/group-matches", json={**payload, "boards": 9}, headers=_h(a[1])
            ).status_code
            == 400
        )
        # Tre tavolieri non ci stanno: gli eleggibili di Alfieri sono 2 (gm_e è fuori).
        assert (
            client.post(
                "/group-matches", json={**payload, "boards": 3}, headers=_h(a[1])
            ).status_code
            == 409
        )

        match = client.post("/group-matches", json=payload, headers=_h(a[1]))
        assert match.status_code == 201
        mid = match.json()["id"]
        assert (
            client.post("/group-matches", json=payload, headers=_h(a[1])).status_code == 409
        )  # una pendente per coppia di gruppi
        assert any("sfida il tuo gruppo" in t for t in _texts(client, c[1]))

        # Accetta solo un manager dello SFIDATO.
        assert client.post(f"/group-matches/{mid}/accept", headers=_h(a[1])).status_code == 403
        assert client.post(f"/group-matches/{mid}/accept", headers=_h(d[1])).status_code == 403
        detail = client.post(f"/group-matches/{mid}/accept", headers=_h(c[1])).json()
        assert detail["status"] == "running"
        rows = detail["board_rows"]
        assert len(rows) == 2 and all(r["session_id"] for r in rows)
        # Formazioni per Elo (pari) → alias; overlap escluso; colori alternati.
        aliases = {r["board"]: (r["x_alias"], r["o_alias"]) for r in rows}
        assert aliases[1] == ("gm_a", "gm_c")  # tavolo dispari: sfidante in X
        assert aliases[2] == ("gm_d", "gm_b")  # tavolo pari: sfidato in X
        assert all("gm_e" not in r for r in aliases.values())
        assert any("giochi al tavolo" in t for t in _texts(client, b[1]))

        # Tavolo 1: matto del matto → vince gm_c (O, Torri). Tavolo 2: patta.
        # Le sessioni sono A DISTANZA: ogni mossa vuole il token di chi muove.
        movers = [a, c, a, c]  # x=gm_a alle semimosse dispari, o=gm_c alle pari
        for uci, mover in zip(FOOLS_MATE, movers):
            out = client.post(
                f"/sessions/{rows[0]['session_id']}/move",
                json={"move": uci},
                headers=_h(mover[1]),
            )
            assert out.status_code == 200
        client.post(
            f"/sessions/{rows[1]['session_id']}/draw",
            json={"side": "x", "action": "offer"},
            headers=_h(d[1]),  # tavolo pari: lo sfidato (gm_d) ha il primo tratto
        )
        client.post(
            f"/sessions/{rows[1]['session_id']}/draw",
            json={"side": "o", "action": "accept"},
            headers=_h(b[1]),
        )

        final = client.get(f"/group-matches/{mid}").json()
        assert final["status"] == "finished"
        assert final["points"] == {"challenger": 0.5, "opponent": 1.5}
        assert final["winner_group"] == "Torri"
        assert any("batte" in t and "Torri" in t for t in _texts(client, a[1]))

        # Bilancio dei gruppi: Torri 1 vinta, Alfieri 1 persa.
        rec_b = client.get("/group-matches", params={"group_id": gb}).json()["record"]
        assert rec_b == {"matches": 1, "won": 1, "drawn": 0, "lost": 0}
        rec_a = client.get("/group-matches", params={"group_id": ga}).json()["record"]
        assert rec_a["lost"] == 1


def test_group_match_decline_and_cancel():
    with TestClient(app) as client:
        a = _login(client, "gn_a")
        b = _login(client, "gn_b")
        c = _login(client, "gn_c")
        d = _login(client, "gn_d")
        ga = _found_group(client, "Cavalli", a, b)
        gb = _found_group(client, "Pedoni", c, d)
        payload = {
            "game_code": "chess",
            "challenger_group_id": ga,
            "opponent_group_id": gb,
            "boards": 1,
        }
        mid = client.post("/group-matches", json=payload, headers=_h(a[1])).json()["id"]
        out = client.post(f"/group-matches/{mid}/decline", headers=_h(c[1])).json()
        assert out["status"] == "declined"
        assert any("ha rifiutato la sfida di gruppo" in t for t in _texts(client, a[1]))
        # Rifiutata: non si accetta né si rifiuta di nuovo.
        assert client.post(f"/group-matches/{mid}/accept", headers=_h(c[1])).status_code == 409

        mid2 = client.post("/group-matches", json=payload, headers=_h(a[1])).json()["id"]
        assert client.post(f"/group-matches/{mid2}/cancel", headers=_h(c[1])).status_code == 403
        out = client.post(f"/group-matches/{mid2}/cancel", headers=_h(a[1])).json()
        assert out["status"] == "cancelled"
        assert client.get("/group-matches/999999").status_code == 404
