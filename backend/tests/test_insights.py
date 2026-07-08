"""Statistiche avanzate e raccolta delle mosse geniali (con screenshot PNG)."""

import json

from app.database import SessionLocal
from app.main import app
from app.models import GameSession
from fastapi.testclient import TestClient

FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]  # X perde in 4 semimosse


def _user(client, alias):
    return client.post(
        "/users",
        json={"first_name": "S", "last_name": "T", "alias": alias, "email": f"{alias}@e.it"},
    ).json()


def _fools_mate(client, x_id, o_id):
    sid = client.post(
        "/sessions",
        json={
            "game_code": "chess",
            "x": {"type": "human", "user_id": x_id},
            "o": {"type": "human", "user_id": o_id},
        },
    ).json()["id"]
    for uci in FOOLS_MATE:
        client.post(f"/sessions/{sid}/move", json={"move": uci})
    return sid


def _stamp_brilliancy(sid: int, ply: int):
    """Inietta il badge 🌟 su una semimossa (il commentatore vero usa Stockfish)."""
    db = SessionLocal()
    try:
        session = db.get(GameSession, sid)
        moves = json.loads(session.moves_json)
        moves[ply - 1]["quality"] = {"symbol": "🌟", "label": "da maestro", "loss": 0}
        session.moves_json = json.dumps(moves)
        db.commit()
    finally:
        db.close()


def test_insights_streaks_and_finish_reasons():
    with TestClient(app) as client:
        u1, u2 = _user(client, "ins_a"), _user(client, "ins_b")
        _fools_mate(client, u1["id"], u2["id"])  # u2 vince (matto)
        _fools_mate(client, u1["id"], u2["id"])  # u2 vince ancora
        # Terza partita: u1 abbandona subito.
        sid = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": u1["id"]},
                "o": {"type": "human", "user_id": u2["id"]},
            },
        ).json()["id"]
        client.post(f"/sessions/{sid}/resign", json={"side": "x"})

        st = client.get(f"/users/{u2['id']}/insights").json()
        chess_row = next(g for g in st["games"] if g["game_code"] == "chess")
        assert chess_row["wins"] == 3
        assert chess_row["best_win_streak"] == 3
        assert chess_row["current_win_streak"] == 3
        assert st["chess"]["finish_reasons"]["mate"] == 2
        assert st["chess"]["finish_reasons"]["resign"] == 1
        # Lo sconfitto ha la serie a zero.
        loser = client.get(f"/users/{u1['id']}/insights").json()
        loser_row = next(g for g in loser["games"] if g["game_code"] == "chess")
        assert loser_row["current_win_streak"] == 0
        assert client.get("/users/999999/insights").status_code == 404


def test_brilliancies_collection_and_badges_count():
    with TestClient(app) as client:
        u1, u2 = _user(client, "ins_c"), _user(client, "ins_d")
        sid = _fools_mate(client, u1["id"], u2["id"])
        _stamp_brilliancy(sid, 4)  # la mossa del matto (giocata da O = u2)

        # NB: il commentatore VERO gira nei test (Stockfish in PATH, sincrono)
        # e può assegnare altri 🌟 reali: si verifica la PRESENZA della mossa
        # marcata, non il conteggio esatto.
        gems = client.get(f"/users/{u2['id']}/brilliancies").json()["brilliancies"]
        gem = next(g for g in gems if g["ply"] == 4 and g["session_id"] == sid)
        assert gem["notation"].startswith("Q")
        assert gem["opponent"] == "ins_c"  # l'avversario umano per alias
        assert gem["result"] == "win"
        # Le mosse di u2 non compaiono nella raccolta di u1 (che ha mosso f3/g4).
        for other in client.get(f"/users/{u1['id']}/brilliancies").json()["brilliancies"]:
            assert other["ply"] % 2 == 1  # solo semimosse del Bianco (u1)
        # Il cruscotto conta il badge marcato (almeno quello).
        st = client.get(f"/users/{u2['id']}/insights").json()
        assert st["chess"]["badges"]["🌟"] >= 1
        assert st["chess"]["brilliancies"] == st["chess"]["badges"]["🌟"]


def test_board_png_snapshot():
    with TestClient(app) as client:
        u1, u2 = _user(client, "ins_e"), _user(client, "ins_f")
        sid = _fools_mate(client, u1["id"], u2["id"])
        resp = client.get(f"/sessions/{sid}/board.png", params={"ply": 4})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"  # firma PNG
        assert len(resp.content) > 1000  # un'immagine vera, non un placeholder
        # Semimossa fuori dallo storico e sessione inesistente.
        assert client.get(f"/sessions/{sid}/board.png", params={"ply": 99}).status_code == 400
        assert client.get("/sessions/999999/board.png").status_code == 404


def test_brilliancy_against_ai_shows_ai_label():
    with TestClient(app) as client:
        u = _user(client, "ins_g")
        sid = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": u["id"]},
                "o": {"type": "ai", "level": "novizio"},
            },
        ).json()["id"]
        # L'umano gioca una mossa (l'IA risponde in sincrono nei test).
        client.post(f"/sessions/{sid}/move", json={"move": "e2e4"})
        # Si chiude d'ufficio per rendere la sessione conclusa.
        client.post(f"/sessions/{sid}/resign", json={"side": "x"})
        _stamp_brilliancy(sid, 1)
        gems = client.get(f"/users/{u['id']}/brilliancies").json()["brilliancies"]
        gem = next(g for g in gems if g["ply"] == 1 and g["session_id"] == sid)
        assert "Novizio" in gem["opponent"]  # etichetta del concorrente IA
        assert gem["result"] == "loss"


def test_sacrifice_detection_via_see():
    """💎: la mossa forte che OFFRE materiale si riconosce con la SEE."""
    from types import SimpleNamespace

    from app.commentary import _is_sacrifice

    from engine import get_game

    game = get_game("chess")
    # Donna prende un pedone DIFESO: dopo Qxe5, dxe5 vince ~8 pedoni netti.
    fake = SimpleNamespace(start_fen="4k3/8/3p4/4p2Q/8/8/8/4K3 w - - 0 1")
    assert _is_sacrifice(game, fake, ["h5e5"]) is True
    # Donna prende un pedone INDIFESO: nessun attaccante sulla casa → non è un sacrificio.
    fake2 = SimpleNamespace(start_fen="4k3/8/8/4p2Q/8/8/8/4K3 w - - 0 1")
    assert _is_sacrifice(game, fake2, ["h5e5"]) is False
    # Storico non ricostruibile: prudente, mai un badge sbagliato.
    assert _is_sacrifice(game, fake, ["a1a8"]) is False


def test_classify_diamond_badge():
    from app.commentary import _classify

    sym, label = _classify(0, is_best=True, capture=True, retreat=False, sacrifice=True)
    assert sym == "💎" and "sacrificio" in label
    # Anche una quasi-migliore col sacrificio è geniale...
    assert _classify(20, is_best=False, capture=True, retreat=False, sacrifice=True)[0] == "💎"
    # ...ma un sacrificio SBAGLIATO resta un blunder.
    assert _classify(250, is_best=False, capture=True, retreat=False, sacrifice=True)[0] == "🤡"


def test_diamond_in_brilliancies_with_piece_filter_fields():
    with TestClient(app) as client:
        u1, u2 = _user(client, "ins_h"), _user(client, "ins_i")
        sid = _fools_mate(client, u1["id"], u2["id"])
        db = SessionLocal()
        try:
            session = db.get(GameSession, sid)
            moves = json.loads(session.moves_json)
            moves[3]["quality"] = {"symbol": "💎", "label": "geniale (sacrificio)", "loss": 0}
            session.moves_json = json.dumps(moves)
            db.commit()
        finally:
            db.close()
        gems = client.get(f"/users/{u2['id']}/brilliancies").json()["brilliancies"]
        gem = next(g for g in gems if g["ply"] == 4 and g["session_id"] == sid)
        assert gem["symbol"] == "💎"
        assert gem["piece"] == "Q"  # Qd8-h4#: campo per i filtri della galleria
        st = client.get(f"/users/{u2['id']}/insights").json()
        assert st["chess"]["badges"]["💎"] >= 1
        assert st["chess"]["brilliancies"] >= st["chess"]["badges"]["💎"]
