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
                    "subcategories": {
                        "conceded": 4,
                        "missed_mates": 1,
                        "hanging": {"total": 1, "minor": 1, "rook": 0, "queen": 0},
                        "check_tactics": 1,
                        "quiet_tactics": 1,
                        "poisoned_captures": 1,
                    },
                },
                "strategy": {"moves": 1, "acpl": 30.0, "score": None},
                "endgame": {"moves": 0, "acpl": None, "score": None},
            },
            "peer_comparison": {
                "band_lo": 1400,
                "band_hi": 1600,
                "elo": 1500,
                "peers": 4,
                "metrics": {
                    "acpl": {"mine": 48.3, "band_avg": 62.0, "better_than": 0.75},
                    "blunders_per_game": {"mine": 0.5, "band_avg": 1.2, "better_than": 1.0},
                },
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
    assert "matti mancati" in html and "catture avvelenate" in html  # dettaglio tattico
    assert "Confronto coi pari fascia" in html
    assert "75% dei pari fascia" in html  # percentile ACPL nella fascia 1400-1600

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


def test_community_is_slim_and_notifications_page_marks_read(monkeypatch):
    """Fase 4: la community è la landing d'area (online + rimandi) SENZA
    sfide/notifiche/dirette/partite; le notifiche vivono in /notifiche/,
    che le elenca e le segna lette; il JSON del heartbeat porta unread."""
    import web.api_client as api

    monkeypatch.setattr(
        api,
        "community_online",
        lambda: {"online": [{"id": 1, "alias": "me", "universal_points": 12}]},
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
    assert "Giocatori online" in html and 'id="online"' in html
    assert "Classifiche" in html  # i rimandi d'area
    # Le sezioni migrate NON ci sono più (vivono negli hub e in /notifiche/).
    assert "Sfide in attesa" not in html
    assert 'id="notifiche"' not in html and 'id="dirette"' not in html
    assert "Le tue partite in corso" not in html
    assert not marked.get("done")  # la community NON segna più le notifiche

    html = client.get("/notifiche/", SERVER_NAME="localhost").content.decode()
    assert "ch_a ti sfida a Scacchi" in html and "Hai vinto il torneo" in html
    assert marked.get("done")  # aprire la PAGINA NOTIFICHE le segna lette

    # Da anonimi la pagina notifiche rimanda al login.
    assert Client().get("/notifiche/", SERVER_NAME="localhost").status_code == 302

    monkeypatch.setattr(api, "heartbeat", lambda t: None)
    data = client.get("/community.json", SERVER_NAME="localhost").json()
    assert data["unread"] == 2  # la campanella in navbar legge questo campo
    assert "my_games" not in data  # snellito: le partite vivono nell'hub Gioca


def test_challenge_form_renders(monkeypatch):
    import web.api_client as api

    monkeypatch.setattr(api, "get_user", lambda uid: {"id": 9, "alias": "rivale"})
    monkeypatch.setattr(
        api, "list_games", lambda: [{"code": "chess", "name": "Scacchi", "playable": True}]
    )
    client = _logged_client()
    html = client.get("/sfide/nuova/9/", SERVER_NAME="localhost").content.decode()
    assert "rivale" in html and "Manda la sfida" in html


def test_group_match_pages_render(monkeypatch):
    """Scheda gruppo con sfide di squadra e pagina della sfida coi tavolieri."""
    import web.api_client as api

    match = {
        "id": 4,
        "game_code": "chess",
        "game_name": "Scacchi",
        "challenger_group_id": 3,
        "challenger_group": "Alfieri",
        "opponent_group_id": 5,
        "opponent_group": "Torri",
        "boards": 2,
        "status": "finished",
        "created_by": 1,
        "points": {"challenger": 0.5, "opponent": 1.5},
        "winner_group": "Torri",
        "created_at": "2026-07-09T12:00:00",
        "board_rows": [
            {
                "board": 1,
                "x_user_id": 1,
                "x_alias": "gm_a",
                "o_user_id": 3,
                "o_alias": "gm_c",
                "session_id": 21,
                "result": "o",
            },
            {
                "board": 2,
                "x_user_id": 4,
                "x_alias": "gm_d",
                "o_user_id": 2,
                "o_alias": "gm_b",
                "session_id": 22,
                "result": "draw",
            },
        ],
    }
    group = {
        "id": 3,
        "name": "Alfieri",
        "created_at": "2026-07-09T10:00:00",
        "members": [{"user_id": 1, "alias": "gm_a", "role": "founder"}],
    }
    monkeypatch.setattr(api, "group_detail", lambda gid: group)
    monkeypatch.setattr(api, "group_ranking", lambda gid, code=None: {"ranking": []})
    monkeypatch.setattr(
        api, "list_games", lambda: [{"code": "chess", "name": "Scacchi", "playable": True}]
    )
    monkeypatch.setattr(api, "list_human_tournaments", lambda **k: {"tournaments": []})
    monkeypatch.setattr(
        api,
        "list_group_matches",
        lambda gid: {
            "matches": [match],
            "record": {"matches": 1, "won": 0, "drawn": 0, "lost": 1},
        },
    )
    monkeypatch.setattr(api, "list_users", lambda: [])
    monkeypatch.setattr(
        api,
        "list_groups",
        lambda: [
            {"id": 3, "name": "Alfieri", "members": []},
            {"id": 5, "name": "Torri", "members": []},
        ],
    )
    monkeypatch.setattr(api, "group_match", lambda mid: match)

    client = _logged_client()
    html = client.get("/gruppi/3/", SERVER_NAME="localhost").content.decode()
    assert "Sfide gruppo-vs-gruppo" in html
    assert "Torri" in html and "0V 0N 1P" in html

    html = client.get("/gruppi/sfide/4/", SERVER_NAME="localhost").content.decode()
    assert "gm_a" in html and "gm_d" in html
    assert "½–½" in html  # il tavolo 2 è finito patto
    assert "Vince «Torri»" in html


def test_watch_page_and_live_section_render(monkeypatch):
    """La pagina spettatore si rende (live e replay) e la community elenca le dirette."""
    import web.api_client as api

    finished = {
        "id": 31,
        "game_code": "chess",
        "game_name": "Scacchi",
        "move_type": "chess",
        "rows": 8,
        "cols": 8,
        "board": [None] * 64,
        "status": "finished",
        "winner": "o",
        "finish_reason": None,
        "current": 0,
        "clock": None,
        "status_line": None,
        "moves": [{"ply": 1, "id": "e2e4", "notation": "e2-e4", "player": "X"}],
        "players": {
            "x": {"type": "human", "user_id": 1, "alias": "sp_a"},
            "o": {"type": "human", "user_id": 2, "alias": "sp_b"},
        },
    }
    monkeypatch.setattr(api, "get_session", lambda sid: finished)
    html = Client().get("/partite/31/guarda/", SERVER_NAME="localhost").content.decode()
    assert "modalità spettatore" in html
    assert "Riproduci" in html  # i controlli del replay animato
    assert "Apri come giocatore" in html

    monkeypatch.setattr(api, "community_online", lambda: {"online": []})
    monkeypatch.setattr(
        api,
        "community_live",
        lambda: {
            "live": [
                {
                    "session_id": 31,
                    "game_code": "chess",
                    "game_name": "Scacchi",
                    "x_label": "sp_a",
                    "o_label": "sp_b",
                    "plies": 12,
                    "tc_category": "blitz",
                    "ai_only": False,
                }
            ]
        },
    )
    # Fase 4: le dirette NON stanno più nella community ma nell'hub «Guarda».
    monkeypatch.setattr(api, "community_recent", lambda: {"recent": []})
    monkeypatch.setattr(api, "arena_tournaments", lambda: [])
    html = Client().get("/guarda/", SERVER_NAME="localhost").content.decode()
    assert "Partite in diretta" in html
    assert "sp_a — sp_b" in html and "Guarda" in html


def test_play_page_connect4_has_c4_board_and_aria_strings(monkeypatch):
    """La pagina di gioco del Forza 4 porta il tavoliere dedicato (c4-board) e
    i nomi dei dischi per le etichette ARIA (pedina rossa/gialla)."""
    import web.api_client as api

    session = {
        "id": 41,
        "game_code": "connect4",
        "game_name": "Forza 4",
        "move_type": "column",
        "rows": 6,
        "cols": 7,
        "board": [None] * 42,
        "status": "in_progress",
        "winner": None,
        "finish_reason": None,
        "current": "x",
        "clock": None,
        "status_line": None,
        "moves": [],
        "legal_moves": [0, 1, 2, 3, 4, 5, 6],
        "remote": False,
        "players": {
            "x": {"type": "human", "user_id": 1, "alias": "c4_a"},
            "o": {"type": "ai"},
        },
    }
    monkeypatch.setattr(api, "get_session", lambda sid: session)
    monkeypatch.setattr(api, "get_config", lambda: {})
    html = Client().get("/partite/41/", SERVER_NAME="localhost").content.decode()
    assert "c4-board" in html  # classe del tavoliere blu coi fori
    assert "pedina rossa" in html and "pedina gialla" in html  # ARIA dei dischi
    # La pagina spettatore usa lo stesso tavoliere.
    html = Client().get("/partite/41/guarda/", SERVER_NAME="localhost").content.decode()
    assert "c4-board" in html


def test_play_page_ships_othello_and_gomoku_boards(monkeypatch):
    """La pagina di gioco porta gli stili dei tavolieri nuovi (panno verde
    dell'Othello, goban del Gomoku) e li aggancia dal game_code."""
    import web.api_client as api

    session = {
        "id": 42,
        "game_code": "othello",
        "game_name": "Othello",
        "move_type": "cell",
        "rows": 8,
        "cols": 8,
        "board": [None] * 64,
        "status": "in_progress",
        "winner": None,
        "finish_reason": None,
        "current": "x",
        "clock": None,
        "status_line": "● 2 — ○ 2",
        "moves": [],
        "legal_moves": [19, 26, 37, 44],
        "remote": False,
        "players": {
            "x": {"type": "human", "user_id": 1, "alias": "oth_a"},
            "o": {"type": "ai"},
        },
    }
    monkeypatch.setattr(api, "get_session", lambda sid: session)
    monkeypatch.setattr(api, "get_config", lambda: {})
    html = Client().get("/partite/42/", SERVER_NAME="localhost").content.decode()
    assert "oth-board" in html and "gmk-board" in html  # stili dei tavolieri
    assert "legalCells" in html  # solo le celle legali sono giocabili
    # Accessibilità: coordinate attorno al tavoliere (notazione del log) e celle
    # esplorabili da tastiera (aria-disabled, mai disabled).
    assert "gameCoords" in html and "coordFrame" in html
    assert "cell-off" in html and "aria-disabled" in html
    html = Client().get("/partite/42/guarda/", SERVER_NAME="localhost").content.decode()
    assert "gameCoords" in html  # coordinate anche per lo spettatore


def test_navbar_has_five_areas_and_no_flat_admin():
    """La navbar è a 5 AREE con menu a discesa (modello chess.com): Gioca,
    Puzzle, Impara, Guarda, Community; Admin non è più una voce di primo
    livello (vive nel menu profilo, quindi assente per gli anonimi)."""
    html = Client().get("/accedi/", SERVER_NAME="localhost").content.decode()
    for label in ("Gioca", "Puzzle", "Impara", "Guarda", "Community"):
        assert label in html
    assert 'id="menu-gioca"' in html and 'id="menu-guarda"' in html
    assert 'id="menu-community"' in html
    assert 'id="nav-burger"' in html  # hamburger mobile
    assert "aria-expanded" in html  # pattern disclosure accessibile
    # Niente Admin al primo livello per gli anonimi (era una voce fissa).
    assert 'href="/admin/"' not in html
    # Le voci ricollocate esistono nei menu: Tornei/Registra/Arena/Classifiche.
    for label in ("Tornei", "Registra partita", "Arena IA", "Classifiche"):
        assert label in html


def test_notifications_json_anonymous_is_empty():
    data = Client().get("/notifiche.json", SERVER_NAME="localhost").json()
    assert data == {"notifications": [], "unread": 0}


def test_navbar_search_filters_players_and_jumps_to_single_match(monkeypatch):
    """La ricerca in navbar filtra i giocatori (?q=); un solo risultato porta
    dritti alla scheda; le pagine di sottolivello hanno il breadcrumb d'area."""
    import web.api_client as api

    people = [
        {"id": 1, "alias": "MagnusFan", "first_name": "Magnus", "last_name": "F"},
        {"id": 2, "alias": "HikaruFan", "first_name": "Hikaru", "last_name": "N"},
        {"id": 3, "alias": "magnete", "first_name": "Aldo", "last_name": "Magni"},
    ]
    monkeypatch.setattr(api, "list_users", lambda: people)
    html = Client().get("/giocatori/?q=magn", SERVER_NAME="localhost").content.decode()
    assert "MagnusFan" in html and "magnete" in html and "HikaruFan" not in html
    assert "Risultati per" in html
    # Con l'input di navbar presente in ogni pagina.
    assert 'role="search"' in html
    # Un solo risultato: dritti alla scheda del giocatore.
    resp = Client().get("/giocatori/?q=hikaru", SERVER_NAME="localhost")
    assert resp.status_code == 302 and resp.url == "/giocatori/2/"
    # Breadcrumb d'area sulla pagina giocatori.
    assert 'class="crumbs"' in html and "Community" in html


def test_home_is_dashboard_for_logged_and_showcase_for_anonymous(monkeypatch):
    """Fase 5: la home del loggato è il CRUSCOTTO (riprendi, sfide, dirette,
    notifiche); per l'anonimo resta la vetrina con la registrazione."""
    import web.api_client as api

    monkeypatch.setattr(
        api, "list_games", lambda: [{"code": "chess", "name": "Scacchi", "is_stochastic": False}]
    )
    html = Client().get("/", SERVER_NAME="localhost").content.decode()
    assert "Crea un giocatore" in html  # vetrina per gli anonimi
    assert "Tocca a te!" not in html

    monkeypatch.setattr(
        api,
        "my_games",
        lambda t: {
            "games": [
                {
                    "session_id": 88,
                    "game_name": "Gomoku",
                    "opponent": "rivale",
                    "my_turn": True,
                    "remote": True,
                }
            ]
        },
    )
    monkeypatch.setattr(
        api,
        "my_challenges",
        lambda t: {"incoming": [{"id": 4}], "outgoing": []},
    )
    monkeypatch.setattr(
        api,
        "community_live",
        lambda: {
            "live": [
                {
                    "session_id": 31,
                    "game_name": "Scacchi",
                    "x_label": "dash_a",
                    "o_label": "dash_b",
                    "plies": 3,
                    "tc_category": None,
                    "ai_only": False,
                }
            ]
        },
    )
    monkeypatch.setattr(api, "notifications_list", lambda t: {"unread": 3, "notifications": []})
    html = _logged_client().get("/", SERVER_NAME="localhost").content.decode()
    assert "Ciao," in html and "me" in html  # saluto col proprio alias
    assert "Tocca a te!" in html and "/partite/88/" in html  # riprendi
    assert "Sfide in attesa" in html and "Rispondi" in html
    assert "dash_a — dash_b" in html  # dirette in evidenza
    assert "Tutte le notifiche" in html  # banner delle non lette
    assert "Crea un giocatore" not in html  # niente vetrina per il loggato


def test_watch_hub_renders_live_arena_and_replays(monkeypatch):
    """L'hub «Guarda» (/guarda/) mostra dirette, tornei Arena IA e replay."""
    import web.api_client as api

    monkeypatch.setattr(
        api,
        "community_live",
        lambda: {
            "live": [
                {
                    "session_id": 31,
                    "game_name": "Scacchi",
                    "x_label": "liv_a",
                    "o_label": "liv_b",
                    "plies": 12,
                    "tc_category": "blitz",
                    "ai_only": False,
                }
            ]
        },
    )
    monkeypatch.setattr(
        api,
        "community_recent",
        lambda: {
            "recent": [
                {
                    "session_id": 29,
                    "game_name": "Gomoku",
                    "x_label": "rep_a",
                    "o_label": "rep_b",
                    "plies": 50,
                    "winner": "o",
                    "ai_only": True,
                }
            ]
        },
    )
    monkeypatch.setattr(
        api,
        "arena_tournaments",
        lambda: [
            {
                "id": 3,
                "name": "Girone dei motori",
                "game_name": "Othello",
                "status": "running",
                "games_played": 2,
                "games_total": 6,
            }
        ],
    )
    html = Client().get("/guarda/", SERVER_NAME="localhost").content.decode()
    assert "liv_a — liv_b" in html and "/partite/31/guarda/" in html
    assert "Girone dei motori" in html and "2/6" in html
    assert "rep_a — rep_b" in html and "0–1" in html  # replay con l'esito
    assert 'id="dirette"' in html and 'id="replay"' in html


def test_play_hub_renders_for_anonymous_and_logged(monkeypatch):
    """L'hub «Gioca» (/gioca/) mostra azioni e tornei a tutti; partite in corso
    e sfide al giocatore loggato. Il setup è diventato la sottopagina
    /gioca/nuova/ (stesso nome di rotta: i link esistenti seguono)."""
    import web.api_client as api

    monkeypatch.setattr(
        api,
        "list_human_tournaments",
        lambda: {
            "tournaments": [
                {
                    "id": 9,
                    "name": "Coppa Hub",
                    "game_name": "Scacchi",
                    "format": "knockout",
                    "status": "open",
                    "players": [1, 2],
                    "max_players": 16,
                    "group_name": None,
                    "winner": None,
                }
            ]
        },
    )
    html = Client().get("/gioca/", SERVER_NAME="localhost").content.decode()
    assert "Nuova partita" in html and "Registra partita" in html
    assert "Coppa Hub" in html and "iscrizioni aperte" in html
    assert "per vedere le tue partite e ricevere le sfide." in html  # invito al login

    monkeypatch.setattr(
        api,
        "my_games",
        lambda token: {
            "games": [
                {
                    "session_id": 77,
                    "game_name": "Othello",
                    "opponent": "rivale",
                    "my_turn": True,
                    "remote": True,
                }
            ]
        },
    )
    monkeypatch.setattr(
        api,
        "my_challenges",
        lambda token: {
            "incoming": [
                {
                    "id": 5,
                    "from_alias": "sfidante",
                    "game_name": "Gomoku",
                    "side": "x",
                    "time_category": None,
                }
            ],
            "outgoing": [],
        },
    )
    client = _logged_client()
    html = client.get("/gioca/", SERVER_NAME="localhost").content.decode()
    assert "Tocca a te!" in html and "/partite/77/" in html
    assert "sfidante" in html and "Accetta" in html
    # Il setup della nuova partita risponde alla sottopagina.
    assert Client().get("/gioca/nuova/", SERVER_NAME="localhost").status_code == 200
