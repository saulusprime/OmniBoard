"""Sistema puzzle: seed verificato, esecuzione, matto alternativo, generazione."""

import json

from app.database import SessionLocal
from app.main import app
from app.models import GameSession, Puzzle
from fastapi.testclient import TestClient

TOKEN = "test-admin"
FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]


def _login(client, alias):
    client.post(
        "/users",
        json={
            "first_name": "P",
            "last_name": "Z",
            "alias": alias,
            "email": f"{alias}@e.it",
            "password": "segretissima1",
        },
    )
    user = client.post("/auth/login", json={"identifier": alias, "password": "segretissima1"})
    if user.status_code != 200:  # serve l'approvazione del super admin
        uid = client.get("/users").json()
        uid = next(u["id"] for u in uid if u["alias"] == alias)
        client.post(f"/users/{uid}/approve", headers={"X-Admin-Token": TOKEN})
        user = client.post("/auth/login", json={"identifier": alias, "password": "segretissima1"})
    return user.json()["token"]


def test_seed_puzzles_present_and_verified():
    with TestClient(app) as client:
        data = client.get("/puzzles").json()
        manual = [p for p in data["puzzles"] if p["source"] == "manual"]
        assert len(manual) == 5  # tutti i matti autoriali hanno passato la verifica
        assert all(p["theme"] == "matto in 1" for p in manual)
        assert "matto in 1" in data["themes"]


def test_detail_and_correct_attempt_solves():
    with TestClient(app) as client:
        pid = client.get("/puzzles").json()["puzzles"][0]["id"]
        detail = client.get(f"/puzzles/{pid}").json()
        assert detail["to_move"] == "white"
        assert detail["playable"]  # mosse giocabili per il click
        assert len(detail["board"]) == 64

        out = client.post(f"/puzzles/{pid}/attempt", json={"step": 0, "move": "a1a8"}).json()
        assert out["correct"] is True and out["solved"] is True
        assert out["view"]["playable"] == []  # matto: nessuna mossa dopo

        wrong = client.post(f"/puzzles/{pid}/attempt", json={"step": 0, "move": "a1a7"}).json()
        assert wrong["correct"] is False and wrong["solved"] is False
        # Step dispari (tocca all'avversario) e puzzle inesistente.
        assert (
            client.post(f"/puzzles/{pid}/attempt", json={"step": 1, "move": "a1a8"}).status_code
            == 400
        )
        assert client.get("/puzzles/999999").status_code == 404


def test_alternative_mate_is_accepted():
    with TestClient(app) as client:
        # Il puzzle a due torri: la soluzione ufficiale è Rh8#, ma anche Rg8#
        # è matto — il matto alternativo vale come soluzione.
        data = client.get("/puzzles").json()["puzzles"]
        db = SessionLocal()
        try:
            target = None
            for p in data:
                row = db.get(Puzzle, p["id"])
                if row and row.fen.startswith("k7/8/1K6/8/8/8/8/6RR"):
                    target = row.id
                    break
        finally:
            db.close()
        assert target is not None
        out = client.post(f"/puzzles/{target}/attempt", json={"step": 0, "move": "g1g8"}).json()
        assert out["correct"] is True and out["solved"] is True
        # Una mossa che NON matta resta sbagliata anche all'ultimo passo.
        ko = client.post(f"/puzzles/{target}/attempt", json={"step": 0, "move": "g1g7"}).json()
        assert ko["correct"] is False


def test_progress_recorded_with_token():
    with TestClient(app) as client:
        token = _login(client, "pz_user")
        pid = client.get("/puzzles").json()["puzzles"][0]["id"]
        client.post(
            f"/puzzles/{pid}/attempt",
            json={"step": 0, "move": "a1a7"},  # sbagliata: tentativo registrato
            headers={"X-Auth-Token": token},
        )
        client.post(
            f"/puzzles/{pid}/attempt",
            json={"step": 0, "move": "a1a8"},
            headers={"X-Auth-Token": token},
        )
        listed = client.get("/puzzles", headers={"X-Auth-Token": token}).json()["puzzles"]
        me = next(p for p in listed if p["id"] == pid)
        assert me["solved"] is True
        # Da anonimi il campo resta None (nessun progresso).
        anon = client.get("/puzzles").json()["puzzles"]
        assert next(p for p in anon if p["id"] == pid)["solved"] is None


def test_generation_from_analyzed_blunder():
    with TestClient(app) as client:
        token = _login(client, "pz_gen")
        # Una partita vera dell'utente, poi un'analisi FINTA con un ?? alla 2ª.
        uid = client.get("/auth/me", headers={"X-Auth-Token": token}).json()["id"]
        u2 = client.post(
            "/users",
            json={"first_name": "P", "last_name": "Z", "alias": "pz_opp", "email": "pzo@e.it"},
        ).json()
        sid = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": uid},
                "o": {"type": "human", "user_id": u2["id"]},
            },
        ).json()["id"]
        for uci in FOOLS_MATE:
            client.post(f"/sessions/{sid}/move", json={"move": uci})
        db = SessionLocal()
        try:
            session = db.get(GameSession, sid)
            session.analysis_json = json.dumps(
                {
                    "status": "done",
                    "evals": [
                        {"ply": 1, "by": "x", "loss": 0, "tag": None},
                        {"ply": 2, "by": "o", "loss": 350, "tag": "??"},
                        {"ply": 3, "by": "x", "loss": 600, "tag": "??"},
                        {"ply": 4, "by": "o", "loss": 0, "tag": None},
                    ],
                }
            )
            db.commit()
        finally:
            db.close()

        out = client.post("/puzzles/generate", headers={"X-Auth-Token": token}).json()
        assert out["created"] == 2  # un puzzle per ciascun «??» con confutazione
        # I puzzle generati sono legali e giocabili (vista costruibile).
        mine = [p for p in client.get("/puzzles").json()["puzzles"] if p["source"] == "auto"]
        assert len(mine) >= 2
        detail = client.get(f"/puzzles/{mine[-1]['id']}").json()
        assert detail["playable"]
        # Rigenerare non duplica (dedup per partita+semimossa).
        again = client.post("/puzzles/generate", headers={"X-Auth-Token": token}).json()
        assert again["created"] == 0
        # Senza login la generazione è negata.
        assert client.post("/puzzles/generate").status_code == 401
