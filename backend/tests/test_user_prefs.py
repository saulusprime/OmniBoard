"""Test delle opzioni estetiche del giocatore (tema scacchiera, segno del Tris)."""

from app.main import app
from fastapi.testclient import TestClient


def _make_user(client, alias):
    resp = client.post(
        "/users",
        json={"first_name": "P", "last_name": "R", "alias": alias, "email": f"{alias}@e.it"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_update_and_read_prefs():
    with TestClient(app) as client:
        user = _make_user(client, "prefs_u")
        assert user["prefs"] == {}  # nessuna preferenza alla creazione
        updated = client.put(
            f"/users/{user['id']}/prefs",
            json={"board_theme": "legno", "tris_mark": "★"},
        ).json()
        assert updated["board_theme"] == "legno"
        assert updated["tris_mark"] == "★"
        # Persistite: la scheda del giocatore le riporta.
        detail = client.get(f"/users/{user['id']}").json()
        assert detail["prefs"]["board_theme"] == "legno"
        assert detail["prefs"]["tris_mark"] == "★"
        # Svuotare il segno = tornare al default del lato.
        reset = client.put(f"/users/{user['id']}/prefs", json={"tris_mark": ""}).json()
        assert reset["tris_mark"] is None


def test_prefs_validation():
    with TestClient(app) as client:
        user = _make_user(client, "prefs_v")
        bad_theme = client.put(f"/users/{user['id']}/prefs", json={"board_theme": "psichedelico"})
        assert bad_theme.status_code == 400
        bad_mark = client.put(f"/users/{user['id']}/prefs", json={"tris_mark": "Z"})
        assert bad_mark.status_code == 400
        assert client.put("/users/999999/prefs", json={"board_theme": "legno"}).status_code == 404


def test_session_view_exposes_theme_and_marks_with_collision_fallback():
    with TestClient(app) as client:
        x = _make_user(client, "prefs_x")
        o = _make_user(client, "prefs_o")
        # Entrambi scelgono la STESSA stella: il lato O deve ripiegare sul default.
        client.put(f"/users/{x['id']}/prefs", json={"board_theme": "smeraldo", "tris_mark": "★"})
        client.put(f"/users/{o['id']}/prefs", json={"tris_mark": "★"})
        session = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": x["id"]},
                "o": {"type": "human", "user_id": o["id"]},
            },
        ).json()
        assert session["players"]["x"]["mark"] == "★"
        assert session["players"]["o"]["mark"] == "O"  # collisione risolta
        assert session["players"]["x"]["board_theme"] == "smeraldo"
        # Lato IA: default (nessun tema, segno standard).
        vs_ai = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": x["id"]},
                "o": {"type": "ai"},
            },
        ).json()
        assert vs_ai["players"]["o"]["mark"] == "O"
        assert vs_ai["players"]["o"]["board_theme"] is None
