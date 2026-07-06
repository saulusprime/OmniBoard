"""Test del suggerimento mossa (hint): riservato ai principianti, mai nel FIDE."""

from app.main import app
from fastapi.testclient import TestClient

TOKEN = "test-admin"  # impostato in conftest tramite ADMIN_TOKEN


def _user(client, alias):
    return client.post(
        "/users",
        json={"first_name": "P", "last_name": "R", "alias": alias, "email": f"{alias}@e.it"},
    ).json()


def test_hint_returns_a_legal_move_for_beginners():
    with TestClient(app) as client:
        u = _user(client, "hint_b")
        sid = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": u["id"]},
                "o": {"type": "ai"},
            },
        ).json()["id"]
        hint = client.post(f"/sessions/{sid}/hint")
        assert hint.status_code == 200
        data = hint.json()
        legal = client.get(f"/sessions/{sid}").json()["legal_moves"]
        assert int(data["move"]) in legal and data["notation"]


def test_hint_denied_to_experts_and_in_fide_games():
    with TestClient(app) as client:
        ux = _user(client, "hint_x")
        uo = _user(client, "hint_o")
        # ux diventa "esperto" di Tris: 11 vittorie registrate (> soglia 10).
        for _ in range(11):
            client.post(
                "/matches",
                json={
                    "game_code": "tictactoe",
                    "player_a": ux["id"],
                    "player_b": uo["id"],
                    "result": "a",
                },
            )
        sid = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": ux["id"]},
                "o": {"type": "human", "user_id": uo["id"]},
            },
        ).json()["id"]
        expert = client.post(f"/sessions/{sid}/hint")
        assert expert.status_code == 403 and "principianti" in expert.json()["detail"]

        # Formato FIDE ufficiale: suggerimenti mai, anche per i principianti.
        fide = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": uo["id"]},
                "o": {"type": "human", "user_id": ux["id"]},
                "time_category": "fide",
            },
        ).json()["id"]
        resp = client.post(f"/sessions/{fide}/hint")
        assert resp.status_code == 403 and "FIDE" in resp.json()["detail"]


def test_hint_respects_turn_and_switch():
    with TestClient(app) as client:
        u = _user(client, "hint_t")
        sid = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "ai"},
                "o": {"type": "human", "user_id": u["id"]},
            },
        ).json()["id"]
        # Con AI_ASYNC=0 l'IA (X) ha già mosso alla creazione: tocca all'umano → ok.
        assert client.post(f"/sessions/{sid}/hint").status_code in (200, 409)
        # Interruttore globale del super admin.
        client.put(
            "/admin/settings",
            json={"values": {"hints.enabled": "false"}},
            headers={"X-Admin-Token": TOKEN},
        )
        assert client.post(f"/sessions/{sid}/hint").status_code == 403
        client.put(
            "/admin/settings",
            json={"values": {"hints.enabled": "true"}},
            headers={"X-Admin-Token": TOKEN},
        )
