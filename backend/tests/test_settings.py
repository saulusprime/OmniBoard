"""Test dei parametri di programma e dell'interfaccia super admin.

Ogni test che modifica un parametro ripristina il valore di default alla fine, perché
il database è condiviso tra tutti i test del backend.
"""

from app.main import app
from fastapi.testclient import TestClient

TOKEN = "test-admin"  # impostato in conftest tramite ADMIN_TOKEN


def _set(client, values):
    resp = client.put("/admin/settings", headers={"X-Admin-Token": TOKEN}, json={"values": values})
    assert resp.status_code == 200, resp.text


def test_settings_seeded_and_listed():
    with TestClient(app) as client:
        data = client.get("/admin/settings").json()
        keys = {s["key"] for s in data}
        assert {"scoring.points_win", "groups.min_votes_to_found", "ai.move_delay_ms"} <= keys


def test_public_config():
    with TestClient(app) as client:
        cfg = client.get("/config").json()
        assert "ai_move_delay_ms" in cfg
        assert cfg["site_name"]
        # Aspetto: animazione dei pezzi ed effetto sonoro (per la pagina di gioco).
        assert cfg["anim_ms"] == 250
        assert cfg["sound_enabled"] is True
        assert 0 <= cfg["sound_volume"] <= 100


def test_update_requires_token():
    with TestClient(app) as client:
        no_token = client.put("/admin/settings", json={"values": {"scoring.points_win": "5"}})
        assert no_token.status_code == 401
        bad_token = client.put(
            "/admin/settings",
            headers={"X-Admin-Token": "sbagliato"},
            json={"values": {"scoring.points_win": "5"}},
        )
        assert bad_token.status_code == 401


def test_update_rejects_unknown_key():
    with TestClient(app) as client:
        resp = client.put(
            "/admin/settings",
            headers={"X-Admin-Token": TOKEN},
            json={"values": {"non.esiste": "1"}},
        )
        assert resp.status_code == 400


def test_scoring_is_configurable():
    with TestClient(app) as client:
        a = client.post(
            "/users",
            json={"first_name": "P", "last_name": "Q", "alias": "cfg_a", "email": "cfg_a@e.it"},
        ).json()
        b = client.post(
            "/users",
            json={"first_name": "P", "last_name": "Q", "alias": "cfg_b", "email": "cfg_b@e.it"},
        ).json()
        try:
            _set(client, {"scoring.points_win": "5"})
            client.post(
                "/matches",
                json={
                    "game_code": "chess",
                    "player_a": a["id"],
                    "player_b": b["id"],
                    "result": "a",
                },
            )
            detail = client.get(f"/users/{a['id']}").json()
            chess = next(s for s in detail["scores"] if s["game_code"] == "chess")
            assert chess["points"] == 5.0
        finally:
            _set(client, {"scoring.points_win": "3"})  # ripristina il default


def test_disable_registration():
    with TestClient(app) as client:
        try:
            _set(client, {"users.allow_registration": "false"})
            resp = client.post(
                "/users",
                json={
                    "first_name": "No",
                    "last_name": "Reg",
                    "alias": "noreg",
                    "email": "noreg@e.it",
                },
            )
            assert resp.status_code == 403
        finally:
            _set(client, {"users.allow_registration": "true"})  # ripristina
