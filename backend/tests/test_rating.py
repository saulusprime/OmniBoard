"""Rating Elo dei giocatori umani: K adattivo, stagioni, pool separato dalle IA."""

from types import SimpleNamespace

from app import rating
from app.main import app
from fastapi.testclient import TestClient

FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]  # X perde in 4 semimosse
TOKEN = "test-admin"


def _user(client, alias):
    return client.post(
        "/users",
        json={"first_name": "E", "last_name": "L", "alias": alias, "email": f"{alias}@e.it"},
    ).json()


def _play_fools_mate(client, x_id, o_id):
    sid = client.post(
        "/sessions",
        json={
            "game_code": "chess",
            "x": {"type": "human", "user_id": x_id},
            "o": {"type": "human", "user_id": o_id},
        },
    ).json()["id"]
    for uci in FOOLS_MATE:
        assert client.post(f"/sessions/{sid}/move", json={"move": uci}).status_code == 200
    return sid


def test_k_factor_tiers_and_expected():
    assert rating.k_factor(SimpleNamespace(games=0, elo=1500)) == 40  # provvisorio
    assert rating.k_factor(SimpleNamespace(games=30, elo=1500)) == 20
    assert rating.k_factor(SimpleNamespace(games=100, elo=2450)) == 10
    assert abs(rating.expected(1500, 1500) - 0.5) < 1e-9
    assert rating.expected(1700, 1500) > 0.75


def test_human_game_updates_both_ratings():
    with TestClient(app) as client:
        u1, u2 = _user(client, "elo_a"), _user(client, "elo_b")
        _play_fools_mate(client, u1["id"], u2["id"])  # vince u2 (il Nero)
        loser = client.get(f"/users/{u1['id']}/ratings").json()
        winner = client.get(f"/users/{u2['id']}/ratings").json()
        rl = next(r for r in loser["ratings"] if r["game_code"] == "chess")
        rw = next(r for r in winner["ratings"] if r["game_code"] == "chess")
        # Alla pari (1500 vs 1500), K=40: il vincitore guadagna 20, lo sconfitto li perde.
        assert rw["elo"] == 1520 and rl["elo"] == 1480
        assert rw["provisional"] is True  # meno di 30 partite
        assert rw["peak_elo"] == 1520
        assert rl["peak_elo"] == 1500  # il picco non scende mai sotto la partenza
        # La somma si conserva (aggiornamenti simmetrici a stesso K).
        assert rw["elo"] + rl["elo"] == 3000


def test_ai_games_do_not_touch_human_elo():
    with TestClient(app) as client:
        u = _user(client, "elo_c")
        sid = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": u["id"]},
                "o": {"type": "ai", "level": "novizio"},
            },
        ).json()["id"]
        state = client.get(f"/sessions/{sid}").json()
        while state["status"] == "in_progress":
            state = client.post(
                f"/sessions/{sid}/move", json={"move": str(state["legal_moves"][0])}
            ).json()
        ratings = client.get(f"/users/{u['id']}/ratings").json()["ratings"]
        assert ratings == []  # il pool umano resta pulito


def test_same_user_both_sides_is_ignored():
    with TestClient(app) as client:
        u = _user(client, "elo_d")
        _play_fools_mate(client, u["id"], u["id"])
        assert client.get(f"/users/{u['id']}/ratings").json()["ratings"] == []


def test_leaderboard_and_season_change():
    with TestClient(app) as client:
        u1, u2 = _user(client, "elo_e"), _user(client, "elo_f")
        _play_fools_mate(client, u1["id"], u2["id"])
        board = client.get("/rankings/elo/chess").json()
        aliases = [r["alias"] for r in board["rows"]]
        assert aliases.index("elo_f") < aliases.index("elo_e")  # il vincitore sta sopra
        top = board["rows"][aliases.index("elo_f")]
        assert top["provisional"] is True

        # Cambio stagione: si riparte da zero, lo storico resta nella stagione vecchia.
        client.put(
            "/admin/settings",
            headers={"X-Admin-Token": TOKEN},
            json={"values": {"elo.season": "test-s2"}},
        )
        fresh = client.get("/rankings/elo/chess").json()
        assert fresh["season"] == "test-s2"
        assert all(r["alias"] not in ("elo_e", "elo_f") for r in fresh["rows"])
        old = client.get("/rankings/elo/chess", params={"season": "2026"}).json()
        assert any(r["alias"] == "elo_f" for r in old["rows"])
        # Prima partita della nuova stagione: si riparte da 1500.
        _play_fools_mate(client, u1["id"], u2["id"])
        s2 = client.get("/rankings/elo/chess").json()["rows"]
        winner = next(r for r in s2 if r["alias"] == "elo_f")
        assert winner["elo"] == 1520 and winner["games"] == 1
        client.put(
            "/admin/settings",
            headers={"X-Admin-Token": TOKEN},
            json={"values": {"elo.season": "2026"}},
        )


def test_unknown_game_404():
    with TestClient(app) as client:
        assert client.get("/rankings/elo/inesistente").status_code == 404
