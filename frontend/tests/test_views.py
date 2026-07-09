"""Smoke test del frontend Django.

Verifica che la home risponda anche quando il backend non è raggiungibile
(degrado controllato): il frontend non deve andare in errore 500.
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "omniboard_web.settings")
django.setup()

from django.test import Client  # noqa: E402


def test_home_renders_even_if_backend_down():
    # Punta a una porta chiusa per simulare il backend irraggiungibile.
    import web.api_client as api

    api.BASE = "http://127.0.0.1:9"

    # SERVER_NAME="localhost" è in ALLOWED_HOSTS (il test client userebbe "testserver").
    response = Client().get("/", SERVER_NAME="localhost")
    assert response.status_code == 200
    assert b"OmniBoard" in response.content


def test_user_stats_renders_four_aspects(monkeypatch):
    """La sezione «quattro aspetti» si rende in IT e in EN (valida anche il .mo)."""
    import web.api_client as api

    fake_insights = {
        "user_id": 1,
        "alias": "asp_view",
        "season": "2026",
        "games": [],
        "chess": {
            "games": 2,
            "avg_plies": 26.0,
            "by_color": None,
            "quick_loss_rate": 0.0,
            "accuracy": None,
            "finish_reasons": {
                "mate": 1,
                "time": 0,
                "resign": 1,
                "agreement": 0,
                "repetition": 0,
            },
            "by_cadence": [],
            "aspects": {
                "games_analyzed": 2,
                "opening": {"moves": 12, "acpl": 48.3, "book_rate": 0.25, "score": 63},
                "tactics": {
                    "blunders": 1,
                    "per_game": 0.5,
                    "opportunities": 1,
                    "punished": 1,
                    "score": None,
                },
                "strategy": {"moves": 1, "acpl": 30.0, "score": None},
                "endgame": {"moves": 0, "acpl": None, "score": None},
            },
            "badges": {},
            "brilliancies": 0,
        },
    }
    monkeypatch.setattr(api, "get_user_insights", lambda uid: fake_insights)
    monkeypatch.setattr(api, "get_user_brilliancies", lambda uid: {"brilliancies": []})

    response = Client().get("/giocatori/1/statistiche/", SERVER_NAME="localhost")
    assert response.status_code == 200
    html = response.content.decode()
    assert "I quattro aspetti del gioco" in html
    assert "48,3" in html  # l10n italiana dei decimali
    assert "nel libro 25%" in html
    assert "campione insufficiente" in html  # finali senza campione

    # In inglese, dal catalogo compilato.
    response = Client().get(
        "/giocatori/1/statistiche/", SERVER_NAME="localhost", HTTP_ACCEPT_LANGUAGE="en"
    )
    html = response.content.decode()
    assert "The four aspects of the game" in html
    assert "48.3" in html
    assert "quiet moves" in html
    assert "sample too small" in html


def test_tournaments_and_group_pages_render(monkeypatch):
    """Le pagine Tornei (lista+tabellone) e la scheda gruppo si rendono."""
    import web.api_client as api

    games = [{"code": "chess", "name": "Scacchi", "playable": True}]
    t_detail = {
        "id": 7,
        "name": "Coppa Lampo",
        "game_code": "chess",
        "game_name": "Scacchi",
        "format": "knockout",
        "double_round": False,
        "status": "finished",
        "created_by": 1,
        "group_id": None,
        "group_name": None,
        "winner": "kt_c",
        "max_players": 16,
        "players": [
            {"user_id": 1, "alias": "kt_a", "seed": 1},
            {"user_id": 2, "alias": "kt_b", "seed": 2},
            {"user_id": 3, "alias": "kt_c", "seed": 3},
        ],
        "rounds": [
            {
                "round": 1,
                "games": [
                    {
                        "slot": 0,
                        "x_user_id": 1,
                        "x_alias": "kt_a",
                        "o_user_id": None,
                        "o_alias": None,
                        "session_id": None,
                        "result": "x",
                    },
                    {
                        "slot": 1,
                        "x_user_id": 2,
                        "x_alias": "kt_b",
                        "o_user_id": 3,
                        "o_alias": "kt_c",
                        "session_id": 11,
                        "result": "draw",
                    },
                ],
            },
            {
                "round": 2,
                "games": [
                    {
                        "slot": 0,
                        "x_user_id": 1,
                        "x_alias": "kt_a",
                        "o_user_id": 3,
                        "o_alias": "kt_c",
                        "session_id": 12,
                        "result": "o",
                    },
                ],
            },
        ],
    }
    monkeypatch.setattr(api, "list_games", lambda: games)
    monkeypatch.setattr(api, "list_groups", lambda: [])
    monkeypatch.setattr(api, "list_human_tournaments", lambda *a, **k: {"tournaments": [t_detail]})
    monkeypatch.setattr(api, "human_tournament", lambda tid: t_detail)

    html = Client().get("/tornei/", SERVER_NAME="localhost").content.decode()
    assert "Coppa Lampo" in html and "kt_c" in html

    html = Client().get("/tornei/7/", SERVER_NAME="localhost").content.decode()
    assert "Finale" in html  # l'ultimo turno del tabellone
    assert "bye" in html  # il seed 1 passa il primo turno senza giocare
    assert "vince il torneo" in html

    group = {
        "id": 3,
        "name": "Circolo",
        "created_at": "2026-07-09T10:00:00",
        "members": [
            {"user_id": 1, "alias": "grp_a", "role": "founder"},
            {"user_id": 2, "alias": "grp_b", "role": "member"},
        ],
    }
    monkeypatch.setattr(api, "group_detail", lambda gid: group)
    monkeypatch.setattr(
        api,
        "group_ranking",
        lambda gid, code=None: {
            "ranking": [{"user_id": 1, "alias": "grp_a", "role": "founder", "universal_points": 9}]
        },
    )
    monkeypatch.setattr(api, "list_users", lambda: [])
    html = Client().get("/gruppi/3/", SERVER_NAME="localhost").content.decode()
    assert "Circolo" in html and "fondatore" in html
    assert "Classifica del gruppo" in html


def _logged_client():
    """Client Django con la sessione (su cookie firmato) di un utente loggato."""
    from django.conf import settings

    client = Client()
    session = client.session
    session["auth_token"] = "tok"
    session["auth_user"] = {"id": 1, "alias": "me"}
    session.save()
    # Sessioni su cookie firmato: il test client non scrive il cookie da solo.
    client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
    return client


def test_community_notifications_challenges_and_bell(monkeypatch):
    """La community mostra sfide e notifiche, le segna lette; il JSON porta unread."""
    import web.api_client as api

    monkeypatch.setattr(api, "community_online", lambda: {"online": []})
    monkeypatch.setattr(api, "my_games", lambda t: {"games": []})
    monkeypatch.setattr(
        api,
        "my_challenges",
        lambda t: {
            "incoming": [
                {
                    "id": 5,
                    "from_alias": "ch_a",
                    "to_alias": "me",
                    "game_name": "Scacchi",
                    "side": "o",
                    "time_category": "blitz",
                    "time_base_min": 5,
                    "time_inc_s": 0,
                    "status": "pending",
                }
            ],
            "outgoing": [
                {
                    "id": 6,
                    "from_alias": "me",
                    "to_alias": "ch_b",
                    "game_name": "Dama",
                    "side": "x",
                    "time_category": None,
                    "time_base_min": None,
                    "time_inc_s": 0,
                    "status": "pending",
                }
            ],
        },
    )
    marked = {}
    monkeypatch.setattr(
        api,
        "notifications_list",
        lambda t: {
            "unread": 2,
            "notifications": [
                {
                    "id": 1,
                    "kind": "game_invite",
                    "text": "ch_a ti sfida a Scacchi",
                    "read": False,
                    "session_id": None,
                    "tournament_id": None,
                    "group_id": None,
                    "invite_id": 5,
                    "created_at": "2026-07-09T10:00:00",
                },
                {
                    "id": 2,
                    "kind": "tournament_won",
                    "text": "Hai vinto il torneo «Coppa»!",
                    "read": False,
                    "session_id": None,
                    "tournament_id": 7,
                    "group_id": None,
                    "invite_id": None,
                    "created_at": None,
                },
            ],
        },
    )
    monkeypatch.setattr(
        api, "notifications_read", lambda t, ids=None: marked.setdefault("done", True)
    )
    client = _logged_client()
    html = client.get("/community/", SERVER_NAME="localhost").content.decode()
    assert "ti sfida a" in html and "Accetta" in html and "Ritira" in html
    assert "Hai vinto il torneo" in html
    assert marked.get("done")  # aprire la pagina segna le notifiche come lette

    monkeypatch.setattr(api, "heartbeat", lambda t: None)
    data = client.get("/community.json", SERVER_NAME="localhost").json()
    assert data["unread"] == 2  # la campanella in navbar legge questo campo


def test_challenge_form_renders(monkeypatch):
    import web.api_client as api

    monkeypatch.setattr(api, "get_user", lambda uid: {"id": 9, "alias": "rivale"})
    monkeypatch.setattr(
        api, "list_games", lambda: [{"code": "chess", "name": "Scacchi", "playable": True}]
    )
    client = _logged_client()
    html = client.get("/sfide/nuova/9/", SERVER_NAME="localhost").content.decode()
    assert "rivale" in html and "Manda la sfida" in html
