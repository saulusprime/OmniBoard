"""Gestione gruppi (inviti/ruoli/espulsioni/classifica) e tornei umani."""

from app.main import app
from fastapi.testclient import TestClient

TOKEN = "test-admin"
FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]  # vince il Nero (O)


def _login(client, alias):
    """Utente registrato+approvato; ritorna (id, token)."""
    client.post(
        "/users",
        json={
            "first_name": "G",
            "last_name": "T",
            "alias": alias,
            "email": f"{alias}@e.it",
            "password": "segretissima1",
        },
    )
    out = client.post("/auth/login", json={"identifier": alias, "password": "segretissima1"})
    if out.status_code != 200:  # serve l'approvazione del super admin
        users = client.get("/users").json()
        uid = next(u["id"] for u in users if u["alias"] == alias)
        client.post(f"/users/{uid}/approve", headers={"X-Admin-Token": TOKEN})
        out = client.post("/auth/login", json={"identifier": alias, "password": "segretissima1"})
    data = out.json()
    return data["user"]["id"] if "user" in data else _uid(client, alias), data["token"]


def _uid(client, alias):
    return next(u["id"] for u in client.get("/users").json() if u["alias"] == alias)


def _found_group(client, founder, voter):
    """Fonda un gruppo con la proposta votata (founder propone, voter vota)."""
    prop = client.post(
        "/groups/proposals",
        json={"name": f"Circolo di {founder[0]}", "proposed_by": founder[0], "threshold": 2},
    ).json()
    out = client.post(
        f"/groups/proposals/{prop['id']}/vote", json={"user_id": voter[0], "in_favor": True}
    ).json()
    assert out["status"] == "founded"
    return out["group_id"]


def _h(token):
    return {"X-Auth-Token": token}


def test_group_invites_roles_expulsions_and_ranking():
    with TestClient(app) as client:
        u1 = _login(client, "grp_a")  # fondatore
        u2 = _login(client, "grp_b")  # membro, poi admin
        u3 = _login(client, "grp_c")  # esterno, poi invitato
        gid = _found_group(client, u1, u2)

        # Un member non invita; senza token 401.
        assert (
            client.post(
                f"/groups/{gid}/invites", json={"user_id": u3[0]}, headers=_h(u2[1])
            ).status_code
            == 403
        )
        assert client.post(f"/groups/{gid}/invites", json={"user_id": u3[0]}).status_code == 401

        # Solo il fondatore cambia i ruoli; poi u2 diventa admin e può invitare.
        assert (
            client.post(
                f"/groups/{gid}/members/{u2[0]}/role", json={"role": "admin"}, headers=_h(u2[1])
            ).status_code
            == 403
        )
        out = client.post(
            f"/groups/{gid}/members/{u2[0]}/role", json={"role": "admin"}, headers=_h(u1[1])
        ).json()
        assert {"user_id": u2[0], "role": "admin"}.items() <= next(
            m for m in out["members"] if m["user_id"] == u2[0]
        ).items()

        inv = client.post(f"/groups/{gid}/invites", json={"user_id": u3[0]}, headers=_h(u2[1]))
        assert inv.status_code == 201
        invite_id = inv.json()["id"]
        # Doppio invito pendente → 409; l'invito non è per u2 → 403.
        assert (
            client.post(
                f"/groups/{gid}/invites", json={"user_id": u3[0]}, headers=_h(u2[1])
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/groups/invites/{invite_id}/respond", json={"accept": True}, headers=_h(u2[1])
            ).status_code
            == 403
        )

        # u3 lo vede fra i suoi e accetta: diventa member.
        mine = client.get("/groups/invites/mine", headers=_h(u3[1])).json()
        assert [i["id"] for i in mine] == [invite_id]
        out = client.post(
            f"/groups/invites/{invite_id}/respond", json={"accept": True}, headers=_h(u3[1])
        ).json()
        assert out["status"] == "accepted"
        group = client.get(f"/groups/{gid}").json()
        assert {m["user_id"] for m in group["members"]} == {u1[0], u2[0], u3[0]}

        # Classifica interna (complessiva e per gioco).
        rk = client.get(f"/groups/{gid}/ranking").json()
        assert len(rk["ranking"]) == 3
        rk_chess = client.get(f"/groups/{gid}/ranking", params={"game_code": "chess"}).json()
        assert all("points" in r and "elo" in r for r in rk_chess["ranking"])

        # Espulsioni: l'admin espelle il member; il fondatore non si tocca.
        assert client.delete(f"/groups/{gid}/members/{u1[0]}", headers=_h(u2[1])).status_code == 409
        out = client.delete(f"/groups/{gid}/members/{u3[0]}", headers=_h(u2[1])).json()
        assert {m["user_id"] for m in out["members"]} == {u1[0], u2[0]}
        # Il fondatore non può lasciare il gruppo (DELETE su di sé).
        assert client.delete(f"/groups/{gid}/members/{u1[0]}", headers=_h(u1[1])).status_code == 409

        # Rifiuto e re-invito: la stessa riga torna pendente.
        inv2 = client.post(
            f"/groups/{gid}/invites", json={"user_id": u3[0]}, headers=_h(u1[1])
        ).json()
        assert inv2["id"] == invite_id  # riusa la riga (unicità gruppo+utente)
        out = client.post(
            f"/groups/invites/{invite_id}/respond", json={"accept": False}, headers=_h(u3[1])
        ).json()
        assert out["status"] == "declined"
        assert client.get("/groups/invites/mine", headers=_h(u3[1])).json() == []


def test_knockout_with_bye_and_draw_odds():
    with TestClient(app) as client:
        a = _login(client, "kt_a")  # seed 1 (alias, Elo pari)
        b = _login(client, "kt_b")  # seed 2
        c = _login(client, "kt_c")  # seed 3
        t = client.post(
            "/tournaments",
            json={"game_code": "chess", "name": "Coppa Lampo", "format": "knockout"},
            headers=_h(a[1]),
        ).json()
        tid = t["id"]
        for u in (a, b, c):
            assert client.post(f"/tournaments/{tid}/join", headers=_h(u[1])).status_code == 200
        # Doppia iscrizione → 409; l'avvio spetta all'organizzatore.
        assert client.post(f"/tournaments/{tid}/join", headers=_h(a[1])).status_code == 409
        assert client.post(f"/tournaments/{tid}/start", headers=_h(b[1])).status_code == 403

        detail = client.post(f"/tournaments/{tid}/start", headers=_h(a[1])).json()
        assert detail["status"] == "running"
        r1 = detail["rounds"][0]["games"]
        assert len(r1) == 2
        # Slot 0: il seed 1 ha il BYE (passa subito, senza sessione).
        bye = r1[0]
        assert bye["x_user_id"] == a[0] and bye["o_alias"] is None
        assert bye["result"] == "x" and bye["session_id"] is None
        # Slot 1: 2 contro 3, sessione vera; il seed migliore ha il Bianco.
        match = r1[1]
        assert match["x_user_id"] == b[0] and match["o_user_id"] == c[0]
        sid = match["session_id"]
        assert sid is not None
        # A torneo avviato: niente iscrizioni né abbandoni.
        assert client.post(f"/tournaments/{tid}/join", headers=_h(c[1])).status_code == 409
        assert client.post(f"/tournaments/{tid}/leave", headers=_h(b[1])).status_code == 409

        # PATTA d'accordo: con i draw odds passa il Nero (kt_c).
        client.post(f"/sessions/{sid}/draw", json={"side": "x", "action": "offer"})
        client.post(f"/sessions/{sid}/draw", json={"side": "o", "action": "accept"})
        detail = client.get(f"/tournaments/{tid}").json()
        final = detail["rounds"][1]["games"][0]
        assert final["x_user_id"] == a[0] and final["o_user_id"] == c[0]

        # In finale il matto del matto: vince il Nero (kt_c) → campione.
        for uci in FOOLS_MATE:
            assert (
                client.post(f"/sessions/{final['session_id']}/move", json={"move": uci}).status_code
                == 200
            )
        detail = client.get(f"/tournaments/{tid}").json()
        assert detail["status"] == "finished"
        assert detail["winner"] == "kt_c"


def test_round_robin_standings_and_group_reserved():
    with TestClient(app) as client:
        a = _login(client, "rr_a")
        b = _login(client, "rr_b")
        c = _login(client, "rr_c")
        t = client.post(
            "/tournaments",
            json={"game_code": "chess", "name": "Girone di prova", "format": "round_robin"},
            headers=_h(a[1]),
        ).json()
        tid = t["id"]
        for u in (a, b, c):
            client.post(f"/tournaments/{tid}/join", headers=_h(u[1]))
        detail = client.post(f"/tournaments/{tid}/start", headers=_h(a[1])).json()
        games = detail["rounds"][0]["games"]
        assert len(games) == 3  # ogni coppia una volta
        assert all(g["session_id"] for g in games)

        # Esiti per abbandono: a batte b e c; b batte c.
        by_pair = {(g["x_user_id"], g["o_user_id"]): g["session_id"] for g in games}
        losers = {
            (a[0], b[0]): "o",
            (a[0], c[0]): "o",
            (b[0], c[0]): "o",
        }
        for pair, sid in by_pair.items():
            client.post(f"/sessions/{sid}/resign", json={"side": losers[pair]})

        detail = client.get(f"/tournaments/{tid}").json()
        assert detail["status"] == "finished"
        assert detail["winner"] == "rr_a"
        table = detail["standings"]
        assert [r["alias"] for r in table] == ["rr_a", "rr_b", "rr_c"]
        assert table[0]["wins"] == 2 and table[2]["losses"] == 2

        # Torneo riservato a un gruppo: organizza solo un membro, entra solo un membro.
        gid = _found_group(client, a, b)
        assert (
            client.post(
                "/tournaments",
                json={
                    "game_code": "chess",
                    "name": "Interno",
                    "format": "knockout",
                    "group_id": gid,
                },
                headers=_h(c[1]),
            ).status_code
            == 403
        )
        t2 = client.post(
            "/tournaments",
            json={
                "game_code": "chess",
                "name": "Interno",
                "format": "knockout",
                "group_id": gid,
            },
            headers=_h(a[1]),
        ).json()
        assert client.post(f"/tournaments/{t2['id']}/join", headers=_h(c[1])).status_code == 403
        assert client.post(f"/tournaments/{t2['id']}/join", headers=_h(b[1])).status_code == 200
        # Con un solo iscritto non si parte.
        client.post(f"/tournaments/{t2['id']}/leave", headers=_h(b[1]))
        assert client.post(f"/tournaments/{t2['id']}/start", headers=_h(a[1])).status_code == 409
