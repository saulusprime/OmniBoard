"""Arena delle IA: identità, rating Elo per concorrente, tornei round-robin.

Nei test i tornei girano in SINCRONO (AI_ASYNC=0): la POST risponde a torneo
concluso. Il Tris con budget ridotto tiene le partite rapidissime.
"""

from types import SimpleNamespace

from app import ai_arena
from app.main import app
from fastapi.testclient import TestClient


def test_identity_catalog_and_side_columns_roundtrip():
    codes = [e["code"] for e in ai_arena.identities()]
    assert "ai" in codes and "stockfish" in codes
    assert "motore:novizio" in codes and "stockfish:zeus" in codes
    assert any(c.startswith("ai:") for c in codes)
    assert len(codes) == len(set(codes))
    # side_columns e identity_of sono inversi (per ogni identità del catalogo).
    for code in codes:
        cols = ai_arena.side_columns(code)
        fake = SimpleNamespace(
            x_is_ai=True,
            x_ai_kind=cols["kind"],
            x_ai_level=cols["level"],
            x_ai_provider=cols["provider"],
        )
        assert ai_arena.identity_of(fake, 0) == code
    # Un lato umano non ha identità.
    assert ai_arena.identity_of(SimpleNamespace(x_is_ai=False), 0) is None


def test_elo_expected_and_pairings():
    assert abs(ai_arena._expected(1500, 1500) - 0.5) < 1e-9
    assert ai_arena._expected(1700, 1500) > 0.75
    # Girone singolo di 3: 3 coppie; doppio: 6 (colori invertiti).
    single = ai_arena.build_pairings(["a", "b", "c"], double_round=False)
    assert single == [("a", "b"), ("a", "c"), ("b", "c")]
    double = ai_arena.build_pairings(["a", "b", "c"], double_round=True)
    assert len(double) == 6
    assert ("b", "a") in double


def test_tournament_validation():
    with TestClient(app) as client:
        base = {"game_code": "tictactoe", "participants": ["ai"]}
        assert client.post("/arena/tournaments", json=base).status_code == 400
        bad = {"game_code": "tictactoe", "participants": ["ai", "marziano:x"]}
        resp = client.post("/arena/tournaments", json=bad)
        assert resp.status_code == 400
        assert "sconosciuti" in resp.json()["detail"]
        missing = {"game_code": "inesistente", "participants": ["ai", "motore:medio"]}
        assert client.post("/arena/tournaments", json=missing).status_code == 404


def _rows_by_identity(client, game_code):
    rows = client.get(f"/arena/ranking/{game_code}").json()["rows"]
    return {r["identity"]: r for r in rows}


def test_tournament_runs_and_feeds_ranking():
    with TestClient(app) as client:
        # La classifica è CONDIVISA con le altre partite IA-vs-IA della suite:
        # si misura il DELTA delle due identità, non i valori assoluti.
        before = _rows_by_identity(client, "tictactoe")
        resp = client.post(
            "/arena/tournaments",
            json={
                "game_code": "tictactoe",
                "participants": ["motore:medio", "motore:novizio"],
                "double_round": True,
                "name": "Derby dei motori",
            },
        )
        assert resp.status_code == 201, resp.text
        t = resp.json()
        assert t["name"] == "Derby dei motori"
        assert t["status"] == "finished"  # sincrono nei test
        assert t["games_total"] == 2 and t["games_played"] == 2
        for g in t["games"]:
            assert g["result"] in ("x", "o", "draw")
            assert g["session_id"] is not None
            # Le partite di torneo sono VERE sessioni, consultabili dallo storico.
            session = client.get(f"/sessions/{g['session_id']}").json()
            assert session["status"] == "finished"

        # La classifica del girone copre entrambi i concorrenti su tutte le partite.
        standings = t["standings"]
        assert len(standings) == 2
        assert all(row["games"] == 2 for row in standings)

        # La classifica Elo del gioco si è alimentata: +2 partite a testa.
        after = _rows_by_identity(client, "tictactoe")
        for identity in ("motore:medio", "motore:novizio"):
            played_before = before.get(identity, {}).get("games", 0)
            assert after[identity]["games"] == played_before + 2
        # L'Elo si conserva: la somma delle due identità non cambia (K simmetrico).
        elo_before = sum(before.get(i, {}).get("elo", 1500) for i in after)
        assert abs(sum(r["elo"] for r in after.values()) - elo_before) <= 1

        # Il dettaglio e l'elenco rispondono.
        assert client.get(f"/arena/tournaments/{t['id']}").json()["id"] == t["id"]
        assert any(row["id"] == t["id"] for row in client.get("/arena/tournaments").json())


def test_human_games_do_not_touch_ai_ratings():
    with TestClient(app) as client:
        u = client.post(
            "/users",
            json={"first_name": "A", "last_name": "R", "alias": "arena_u", "email": "ar@e.it"},
        ).json()
        before = client.get("/arena/ranking/tictactoe").json()["rows"]
        sid = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": u["id"]},
                "o": {"type": "ai", "level": "novizio"},
            },
        ).json()["id"]
        # L'umano gioca (l'IA risponde in sincrono) fino alla fine.
        state = client.get(f"/sessions/{sid}").json()
        while state["status"] == "in_progress":
            cell = str(state["legal_moves"][0])
            state = client.post(f"/sessions/{sid}/move", json={"move": cell}).json()
        after = client.get("/arena/ranking/tictactoe").json()["rows"]
        assert before == after  # nessun aggiornamento Elo dalle partite con umani
