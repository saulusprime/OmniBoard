"""Test di registrazione (con approvazione del super admin) e autenticazione.

Flusso coperto: richiesta di registrazione → login negato finché in attesa →
approvazione (solo super admin) → login/me/logout → scadenza sessione.
"""

from app.main import app
from fastapi.testclient import TestClient

TOKEN = "test-admin"  # impostato in conftest tramite ADMIN_TOKEN


def _register(client, alias, password="segretissima1"):
    resp = client.post(
        "/users",
        json={
            "first_name": "P",
            "last_name": "R",
            "alias": alias,
            "email": f"{alias}@e.it",
            "password": password,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_registration_is_a_request_pending_approval():
    with TestClient(app) as client:
        user = _register(client, "auth_pending")
        assert user["is_approved"] is False  # la registrazione è solo una richiesta
        # Login negato finché il super admin non approva (403, non 401: la
        # password è giusta, è la richiesta a non essere ancora accettata).
        resp = client.post(
            "/auth/login",
            json={"identifier": "auth_pending", "password": "segretissima1"},
        )
        assert resp.status_code == 403
        assert "approvazione" in resp.json()["detail"]


def test_only_superadmin_approves_and_login_works_after():
    with TestClient(app) as client:
        user = _register(client, "auth_ok")
        # Senza token (o con token errato) l'approvazione è negata.
        assert client.post(f"/users/{user['id']}/approve").status_code == 401
        assert (
            client.post(
                f"/users/{user['id']}/approve", headers={"X-Admin-Token": "sbagliato"}
            ).status_code
            == 401
        )
        approved = client.post(f"/users/{user['id']}/approve", headers={"X-Admin-Token": TOKEN})
        assert approved.status_code == 200
        assert approved.json()["is_approved"] is True

        # Login con alias; il token di sessione permette /auth/me.
        out = client.post(
            "/auth/login", json={"identifier": "auth_ok", "password": "segretissima1"}
        ).json()
        assert out["token"] and out["user"]["alias"] == "auth_ok"
        me = client.get("/auth/me", headers={"X-Auth-Token": out["token"]})
        assert me.status_code == 200 and me.json()["id"] == user["id"]

        # Login anche con l'email al posto dell'alias.
        by_email = client.post(
            "/auth/login",
            json={"identifier": "auth_ok@e.it", "password": "segretissima1"},
        )
        assert by_email.status_code == 200

        # Logout: il token smette di valere (e il logout è idempotente).
        assert (
            client.post("/auth/logout", headers={"X-Auth-Token": out["token"]}).status_code == 204
        )
        assert client.get("/auth/me", headers={"X-Auth-Token": out["token"]}).status_code == 401
        assert (
            client.post("/auth/logout", headers={"X-Auth-Token": out["token"]}).status_code == 204
        )


def test_bad_credentials_all_look_alike():
    with TestClient(app) as client:
        user = _register(client, "auth_wrong")
        client.post(f"/users/{user['id']}/approve", headers={"X-Admin-Token": TOKEN})
        # Password errata, utente inesistente e utente senza password: stesso 401
        # (nessuna enumerazione degli account).
        wrong = client.post("/auth/login", json={"identifier": "auth_wrong", "password": "no"})
        ghost = client.post("/auth/login", json={"identifier": "nessuno", "password": "x"})
        assert wrong.status_code == ghost.status_code == 401
        assert wrong.json()["detail"] == ghost.json()["detail"]

        # Utente storico senza password: non può accedere.
        nopass = client.post(
            "/users",
            json={
                "first_name": "P",
                "last_name": "R",
                "alias": "auth_nopass",
                "email": "auth_nopass@e.it",
            },
        ).json()
        client.post(f"/users/{nopass['id']}/approve", headers={"X-Admin-Token": TOKEN})
        resp = client.post("/auth/login", json={"identifier": "auth_nopass", "password": ""})
        assert resp.status_code == 401


def test_reject_only_pending_requests():
    with TestClient(app) as client:
        pending = _register(client, "auth_reject")
        # Il rifiuto richiede il token super admin.
        assert client.delete(f"/users/{pending['id']}").status_code == 401
        resp = client.delete(f"/users/{pending['id']}", headers={"X-Admin-Token": TOKEN})
        assert resp.status_code == 204
        assert client.get(f"/users/{pending['id']}").status_code == 404

        # Un giocatore già approvato NON si elimina da qui.
        active = _register(client, "auth_active")
        client.post(f"/users/{active['id']}/approve", headers={"X-Admin-Token": TOKEN})
        resp = client.delete(f"/users/{active['id']}", headers={"X-Admin-Token": TOKEN})
        assert resp.status_code == 409


def test_session_expiry_honours_setting():
    with TestClient(app) as client:
        user = _register(client, "auth_expiry")
        client.post(f"/users/{user['id']}/approve", headers={"X-Admin-Token": TOKEN})
        # Durata sessione 0 ore: il token nasce già scaduto.
        client.put(
            "/admin/settings",
            json={"values": {"users.session_hours": "0"}},
            headers={"X-Admin-Token": TOKEN},
        )
        out = client.post(
            "/auth/login", json={"identifier": "auth_expiry", "password": "segretissima1"}
        ).json()
        assert client.get("/auth/me", headers={"X-Auth-Token": out["token"]}).status_code == 401
        # Ripristina il default per gli altri test.
        client.put(
            "/admin/settings",
            json={"values": {"users.session_hours": "720"}},
            headers={"X-Admin-Token": TOKEN},
        )
