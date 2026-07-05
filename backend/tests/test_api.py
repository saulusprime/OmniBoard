"""Test end-to-end dell'API tramite il TestClient di FastAPI.

Il database è condiviso tra i test (vedi conftest), perciò ogni test usa alias
univoci per evitare collisioni.
"""

from app.main import app
from fastapi.testclient import TestClient


def make_user(client, alias, nationality="IT", region="Lazio"):
    resp = client.post(
        "/users",
        json={
            "first_name": "Test",
            "last_name": "User",
            "alias": alias,
            "email": f"{alias}@example.it",
            "nationality": nationality,
            "region": region,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_health():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_games_seeded():
    with TestClient(app) as client:
        codes = {g["code"] for g in client.get("/games").json()}
        assert {"chess", "checkers", "tictactoe", "connect4", "backgammon"} <= codes


def test_games_playable_flag():
    with TestClient(app) as client:
        games = {g["code"]: g for g in client.get("/games").json()}
        assert games["tictactoe"]["playable"] is True
        assert games["connect4"]["playable"] is True
        assert games["checkers"]["playable"] is True
        assert games["chess"]["playable"] is True
        assert games["backgammon"]["playable"] is True  # primo gioco stocastico


def test_create_user_and_duplicates():
    with TestClient(app) as client:
        user = make_user(client, "dup_alias")
        assert user["alias"] == "dup_alias"

        same_alias = client.post(
            "/users",
            json={
                "first_name": "A",
                "last_name": "B",
                "alias": "dup_alias",
                "email": "diversa@example.it",
            },
        )
        assert same_alias.status_code == 409

        same_email = client.post(
            "/users",
            json={
                "first_name": "A",
                "last_name": "B",
                "alias": "diverso",
                "email": "dup_alias@example.it",
            },
        )
        assert same_email.status_code == 409


def test_invalid_email_rejected():
    with TestClient(app) as client:
        resp = client.post(
            "/users",
            json={
                "first_name": "A",
                "last_name": "B",
                "alias": "bademail",
                "email": "non-una-email",
            },
        )
        assert resp.status_code == 422


def test_match_updates_scores():
    with TestClient(app) as client:
        a = make_user(client, "scorer_a")
        b = make_user(client, "scorer_b")

        resp = client.post(
            "/matches",
            json={"game_code": "chess", "player_a": a["id"], "player_b": b["id"], "result": "a"},
        )
        assert resp.status_code == 201

        detail = client.get(f"/users/{a['id']}").json()
        assert detail["universal_points"] == 3.0
        chess = next(s for s in detail["scores"] if s["game_code"] == "chess")
        assert chess["wins"] == 1
        assert chess["points"] == 3.0


def test_match_same_player_rejected():
    with TestClient(app) as client:
        a = make_user(client, "solo_player")
        resp = client.post(
            "/matches",
            json={"game_code": "chess", "player_a": a["id"], "player_b": a["id"], "result": "a"},
        )
        assert resp.status_code == 400


def test_rankings_scopes():
    """Classifica per gioco con ambito globale, nazionale e regionale."""
    with TestClient(app) as client:
        it1 = make_user(client, "rank_it1", "IT", "Lazio")
        it2 = make_user(client, "rank_it2", "IT", "Lombardia")
        us1 = make_user(client, "rank_us1", "US", None)

        # connect4 è usato solo qui: la classifica resta isolata da altri test.
        client.post(
            "/matches",
            json={
                "game_code": "connect4",
                "player_a": it1["id"],
                "player_b": it2["id"],
                "result": "a",
            },
        )
        client.post(
            "/matches",
            json={
                "game_code": "connect4",
                "player_a": us1["id"],
                "player_b": it2["id"],
                "result": "draw",
            },
        )

        glob = client.get("/rankings/games/connect4?scope=global").json()
        aliases = [e["alias"] for e in glob]
        assert set(aliases) == {"rank_it1", "rank_it2", "rank_us1"}
        assert aliases[0] == "rank_it1"  # 3 punti, in cima

        national = client.get("/rankings/games/connect4?scope=national&country=IT").json()
        assert {e["alias"] for e in national} == {"rank_it1", "rank_it2"}

        regional = client.get("/rankings/games/connect4?scope=regional&region=Lazio").json()
        assert {e["alias"] for e in regional} == {"rank_it1"}


def test_group_founding_via_vote():
    with TestClient(app) as client:
        u1 = make_user(client, "grp_u1")
        u2 = make_user(client, "grp_u2")

        proposal = client.post(
            "/groups/proposals",
            json={"name": "Cavalieri", "proposed_by": u1["id"], "threshold": 2},
        ).json()
        assert proposal["status"] == "pending"
        assert proposal["favor_count"] == 1  # il proponente vota in automatico

        voted = client.post(
            f"/groups/proposals/{proposal['id']}/vote",
            json={"user_id": u2["id"], "in_favor": True},
        ).json()
        assert voted["status"] == "founded"

        groups = client.get("/groups").json()
        group = next(g for g in groups if g["id"] == voted["group_id"])
        roles = {m["alias"]: m["role"] for m in group["members"]}
        assert roles["grp_u1"] == "founder"
        assert roles["grp_u2"] == "member"
