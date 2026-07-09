"""Inviti a giocare (sfide con accettazione) e notifiche persistenti."""

from app.main import app
from fastapi.testclient import TestClient

TOKEN = "test-admin"
FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]  # vince il Nero (O)


def _login(client, alias):
    """Utente registrato+approvato; ritorna (id, token)."""
    client.post(
        "/users",
        json={
            "first_name": "N",
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


def _h(token):
    return {"X-Auth-Token": token}


def _texts(client, token):
    data = client.get("/notifications", headers=_h(token)).json()
    return data["unread"], [n["text"] for n in data["notifications"]]


def test_challenge_flow_with_notifications():
    with TestClient(app) as client:
        a = _login(client, "ch_a")
        b = _login(client, "ch_b")

        # Validazioni: anonimo, auto-sfida, lato strano, doppione.
        assert (
            client.post("/challenges", json={"game_code": "chess", "to_user_id": b[0]})
        ).status_code == 401
        assert (
            client.post(
                "/challenges",
                json={"game_code": "chess", "to_user_id": a[0]},
                headers=_h(a[1]),
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/challenges",
                json={"game_code": "chess", "to_user_id": b[0], "side": "z"},
                headers=_h(a[1]),
            ).status_code
            == 400
        )

        # La sfida parte: lo sfidante sceglie il NERO e una cadenza blitz.
        inv = client.post(
            "/challenges",
            json={
                "game_code": "chess",
                "to_user_id": b[0],
                "side": "o",
                "time_category": "blitz",
                "time_base_min": 5,
            },
            headers=_h(a[1]),
        )
        assert inv.status_code == 201
        invite_id = inv.json()["id"]
        assert (
            client.post(
                "/challenges",
                json={"game_code": "chess", "to_user_id": b[0]},
                headers=_h(a[1]),
            ).status_code
            == 409
        )  # una pendente per coppia+gioco

        # Lo sfidato è stato NOTIFICATO e vede la sfida fra le ricevute.
        unread, texts = _texts(client, b[1])
        assert unread >= 1 and any("ch_a ti sfida a" in t for t in texts)
        mine = client.get("/challenges/mine", headers=_h(b[1])).json()
        assert [i["id"] for i in mine["incoming"]] == [invite_id]
        assert client.get("/challenges/mine", headers=_h(a[1])).json()["outgoing"]

        # Solo lo sfidato accetta; la partita nasce coi colori e l'orologio giusti.
        assert client.post(f"/challenges/{invite_id}/accept", headers=_h(a[1])).status_code == 403
        out = client.post(f"/challenges/{invite_id}/accept", headers=_h(b[1])).json()
        assert out["status"] == "accepted" and out["session_id"]
        session = client.get(f"/sessions/{out['session_id']}").json()
        assert session["players"]["x"]["user_id"] == b[0]  # lo sfidante ha scelto il Nero
        assert session["players"]["o"]["user_id"] == a[0]
        assert session["remote"] is True
        assert session["clock"]["category"] == "blitz"

        # Lo sfidante è notificato dell'accettazione; la sfida non è più pendente.
        _, texts = _texts(client, a[1])
        assert any("ha accettato la tua sfida" in t for t in texts)
        assert client.post(f"/challenges/{invite_id}/accept", headers=_h(b[1])).status_code == 409

        # Rifiuto e ritiro: il rifiuto è notificato, il ritiro è silenzioso.
        inv2 = client.post(
            "/challenges",
            json={"game_code": "tictactoe", "to_user_id": a[0]},
            headers=_h(b[1]),
        ).json()
        client.post(f"/challenges/{inv2['id']}/decline", headers=_h(a[1]))
        _, texts = _texts(client, b[1])
        assert any("ha rifiutato la tua sfida" in t for t in texts)
        inv3 = client.post(
            "/challenges",
            json={"game_code": "tictactoe", "to_user_id": a[0]},
            headers=_h(b[1]),
        ).json()
        assert client.post(f"/challenges/{inv3['id']}/cancel", headers=_h(a[1])).status_code == 403
        assert (
            client.post(f"/challenges/{inv3['id']}/cancel", headers=_h(b[1])).json()["status"]
            == "cancelled"
        )


def test_notifications_read_and_english():
    with TestClient(app) as client:
        a = _login(client, "nt_a")
        b = _login(client, "nt_b")
        client.post(
            "/challenges",
            json={"game_code": "chess", "to_user_id": b[0]},
            headers=_h(a[1]),
        )
        # In inglese il template arriva dal catalogo backend.
        data = client.get("/notifications", headers={**_h(b[1]), "Accept-Language": "en"}).json()
        assert any("challenges you to" in n["text"] for n in data["notifications"])
        assert data["unread"] >= 1
        # Segna tutte come lette: il conteggio si azzera.
        marked = client.post("/notifications/read", json={}, headers=_h(b[1])).json()["marked"]
        assert marked >= 1
        assert client.get("/notifications", headers=_h(b[1])).json()["unread"] == 0
        # Senza token: 401.
        assert client.get("/notifications").status_code == 401


def test_tournament_and_group_notifications():
    with TestClient(app) as client:
        a = _login(client, "ntt_a")
        b = _login(client, "ntt_b")
        # Torneo a 2: all'avvio entrambi ricevono la campanella della partita.
        t = client.post(
            "/tournaments",
            json={"game_code": "chess", "name": "Duello", "format": "knockout"},
            headers=_h(a[1]),
        ).json()
        for u in (a, b):
            client.post(f"/tournaments/{t['id']}/join", headers=_h(u[1]))
        detail = client.post(f"/tournaments/{t['id']}/start", headers=_h(a[1])).json()
        for u in (a, b):
            _, texts = _texts(client, u[1])
            assert any("è pronta la tua partita del turno 1" in x for x in texts)

        # Finale del torneo: vince il Nero (matto del matto) → coppa e verdetto.
        sid = detail["rounds"][0]["games"][0]["session_id"]
        black = detail["rounds"][0]["games"][0]["o_user_id"]
        for uci in FOOLS_MATE:
            client.post(f"/sessions/{sid}/move", json={"move": uci})
        winner, loser = (a, b) if a[0] == black else (b, a)
        _, texts = _texts(client, winner[1])
        assert any("Hai vinto il torneo" in x for x in texts)
        _, texts = _texts(client, loser[1])
        assert any("concluso: vince" in x for x in texts)

        # Invito a un gruppo: notifica all'invitato.
        prop = client.post(
            "/groups/proposals",
            json={"name": "Circolo notifiche", "proposed_by": a[0], "threshold": 2},
        ).json()
        founded = client.post(
            f"/groups/proposals/{prop['id']}/vote",
            json={"user_id": b[0], "in_favor": True},
        ).json()
        c = _login(client, "ntt_c")
        client.post(
            f"/groups/{founded['group_id']}/invites",
            json={"user_id": c[0]},
            headers=_h(a[1]),
        )
        _, texts = _texts(client, c[1])
        assert any("ti invita" in x for x in texts)
