"""Test della modalità asincrona delle mosse IA (worker in background + polling).

La suite gira normalmente in modalità sincrona (``AI_ASYNC=0`` nel conftest); qui la
modalità asincrona viene riattivata con monkeypatch per verificare il flusso reale:
risposta immediata, IA che muove in un thread, client che si aggiorna via polling.
"""

import time

from app.main import app
from fastapi.testclient import TestClient


def _make_user(client, alias):
    resp = client.post(
        "/users",
        json={"first_name": "A", "last_name": "B", "alias": alias, "email": f"{alias}@e.it"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _wait_human_turn(client, sid, timeout=10.0):
    """Polling (come fa il frontend) finché l'IA ha mosso o la partita è finita."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = client.get(f"/sessions/{sid}").json()
        if data["status"] != "in_progress" or not data["current_is_ai"]:
            return data
        time.sleep(0.05)
    raise AssertionError("l'IA non ha mosso entro il timeout")


def test_async_move_runs_in_background_and_polling_sees_it(monkeypatch):
    monkeypatch.setenv("AI_ASYNC", "1")
    with TestClient(app) as client:
        user = _make_user(client, "async_h")
        session = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": user["id"]},
                "o": {"type": "ai"},
            },
        ).json()
        sid = session["id"]

        resp = client.post(f"/sessions/{sid}/move", json={"move": "4"})
        assert resp.status_code == 200
        data = _wait_human_turn(client, sid)  # il worker gioca la risposta dell'IA
        assert data["status"] == "in_progress"
        assert data["current"] == "x"
        assert len(data["moves"]) == 2  # mossa umana + una sola risposta IA
        assert data["moves"][1]["player"] == "O"


def test_schedule_is_idempotent_no_double_moves(monkeypatch):
    monkeypatch.setenv("AI_ASYNC", "1")
    with TestClient(app) as client:
        user = _make_user(client, "async_i")
        # X = IA: la creazione programma il worker; i GET ripetuti (auto-ripristino del
        # polling) non devono accodare mosse doppie.
        session = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "ai"},
                "o": {"type": "human", "user_id": user["id"]},
            },
        ).json()
        sid = session["id"]
        for _ in range(5):
            client.get(f"/sessions/{sid}")
        data = _wait_human_turn(client, sid)
        assert len(data["moves"]) == 1  # esattamente una mossa dell'IA (X)
        assert data["moves"][0]["player"] == "X"
        assert data["current"] == "o"


def test_watch_pace_delays_first_ai_move(monkeypatch):
    """Col ritmo di visione attivo, la prima mossa dell'IA NON è già sulla scacchiera
    alla creazione: il client ha il tempo di disegnarla e vedrà la mossa animata."""
    monkeypatch.setenv("AI_ASYNC", "1")
    monkeypatch.setenv("AI_WATCH_PACE_MS", "1500")
    with TestClient(app) as client:
        user = _make_user(client, "pace_h")
        session = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "ai"},
                "o": {"type": "human", "user_id": user["id"]},
            },
        ).json()
        sid = session["id"]
        # Subito dopo la creazione: il worker sta ancora rispettando il ritmo.
        just_created = client.get(f"/sessions/{sid}").json()
        assert just_created["moves"] == []
        # Poi la mossa arriva (il polling la vedrà singola, animata).
        data = _wait_human_turn(client, sid)
        assert len(data["moves"]) == 1


def test_sync_mode_still_returns_ai_move_inline():
    # Con AI_ASYNC=0 (default della suite) la risposta contiene già la mossa dell'IA.
    with TestClient(app) as client:
        user = _make_user(client, "sync_h")
        session = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": user["id"]},
                "o": {"type": "ai"},
            },
        ).json()
        data = client.post(f"/sessions/{session['id']}/move", json={"move": "4"}).json()
        assert len(data["moves"]) == 2
        assert data["current"] == "x"
