"""Test dell'orologio di gioco degli scacchi (categorie, incrementi, bandierina).

Il passare del tempo si simula spostando ``gameplay._now`` con monkeypatch: i test
restano istantanei e deterministici.
"""

from datetime import timedelta

from app import gameplay
from app.main import app
from fastapi.testclient import TestClient

from engine import get_game


def _make_user(client, alias):
    resp = client.post(
        "/users",
        json={"first_name": "T", "last_name": "C", "alias": alias, "email": f"{alias}@e.it"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _chess_session(client, x_id, o_id, **time_kwargs):
    return client.post(
        "/sessions",
        json={
            "game_code": "chess",
            "x": {"type": "human", "user_id": x_id},
            "o": {"type": "human", "user_id": o_id},
            **time_kwargs,
        },
    )


def _advance_clock(monkeypatch, seconds):
    """Da qui in poi il "adesso" del server è spostato avanti di ``seconds``."""
    real_now = gameplay._now()
    monkeypatch.setattr(gameplay, "_now", lambda: real_now + timedelta(seconds=seconds))


def test_time_control_validation():
    with TestClient(app) as client:
        x = _make_user(client, "tc_x")
        o = _make_user(client, "tc_o")
        # Orologio solo per gli scacchi.
        bad_game = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": x["id"]},
                "o": {"type": "human", "user_id": o["id"]},
                "time_category": "blitz",
            },
        )
        assert bad_game.status_code == 400
        # Range delle categorie: blitz < 15′, rapid 15-60′, classical > 60′.
        assert (
            _chess_session(
                client, x["id"], o["id"], time_category="blitz", time_base_min=20
            ).status_code
            == 400
        )
        assert (
            _chess_session(
                client, x["id"], o["id"], time_category="rapid", time_base_min=10
            ).status_code
            == 400
        )
        assert (
            _chess_session(
                client, x["id"], o["id"], time_category="classical", time_base_min=30
            ).status_code
            == 400
        )
        # FIDE: parametri fissi, niente minuti né incremento personalizzati.
        assert (
            _chess_session(client, x["id"], o["id"], time_category="fide", time_inc_s=5).status_code
            == 400
        )
        assert (
            _chess_session(
                client, x["id"], o["id"], time_category="fide", time_base_min=90
            ).status_code
            == 400
        )
        # Categoria sconosciuta.
        assert _chess_session(client, x["id"], o["id"], time_category="bullet").status_code == 400


def test_clock_in_view_blitz_and_fide():
    with TestClient(app) as client:
        x = _make_user(client, "tcv_x")
        o = _make_user(client, "tcv_o")
        blitz = _chess_session(
            client, x["id"], o["id"], time_category="blitz", time_base_min=3, time_inc_s=2
        ).json()
        assert blitz["clock"] == {
            "category": "blitz",
            "base_s": 180,
            "inc_s": 2,
            "x_ms": blitz["clock"]["x_ms"],
            "o_ms": 180000,
            "running": "x",
        }
        assert 179000 <= blitz["clock"]["x_ms"] <= 180000  # l'orologio di X sta correndo
        # FIDE: 90 minuti e incremento 30″ fissati d'ufficio.
        fide = _chess_session(client, x["id"], o["id"], time_category="fide").json()
        assert fide["clock"]["base_s"] == 5400 and fide["clock"]["inc_s"] == 30
        # Senza orologio: clock assente.
        free = _chess_session(client, x["id"], o["id"]).json()
        assert free["clock"] is None


def test_time_consumed_and_fischer_increment(monkeypatch):
    with TestClient(app) as client:
        x = _make_user(client, "tci_x")
        o = _make_user(client, "tci_o")
        session = _chess_session(
            client, x["id"], o["id"], time_category="blitz", time_base_min=1, time_inc_s=3
        ).json()
        _advance_clock(monkeypatch, 10)  # X pensa 10 secondi...
        after = client.post(f"/sessions/{session['id']}/move", json={"move": "e2e4"}).json()
        # ...quindi: 60000 - 10000 + 3000 (Fischer) ≈ 53000 ms, e ora corre l'orologio di O.
        assert 52500 <= after["clock"]["x_ms"] <= 53100
        assert after["clock"]["running"] == "o"


def test_flag_fall_on_move_and_on_read(monkeypatch):
    with TestClient(app) as client:
        x = _make_user(client, "tcf_x")
        o = _make_user(client, "tcf_o")
        # Bandierina sulla mossa: X muove quando il suo tempo è già finito.
        s1 = _chess_session(client, x["id"], o["id"], time_category="blitz", time_base_min=1).json()
        _advance_clock(monkeypatch, 61)
        late = client.post(f"/sessions/{s1['id']}/move", json={"move": "e2e4"})
        assert late.status_code == 409
        ended = client.get(f"/sessions/{s1['id']}").json()
        assert ended["status"] == "finished"
        assert ended["winner"] == "o"
        assert ended["finish_reason"] == "time"
        # Bandierina pigra: basta una lettura di stato (il polling del client).
        monkeypatch.undo()
        s2 = _chess_session(client, x["id"], o["id"], time_category="blitz", time_base_min=1).json()
        _advance_clock(monkeypatch, 61)
        read = client.get(f"/sessions/{s2['id']}").json()
        assert read["status"] == "finished" and read["finish_reason"] == "time"


def test_fide_bonus_and_bare_king_rules():
    # Bonus: FIDE dà 30″ a mossa e +30′ alla 40ª mossa del giocatore; Fischer dà inc_s.
    assert gameplay._bonus_ms("fide", 30, 39) == 30000
    assert gameplay._bonus_ms("fide", 30, 40) == 30000 + 30 * 60 * 1000
    assert gameplay._bonus_ms("blitz", 3, 12) == 3000
    assert gameplay._bonus_ms("rapid", 0, 5) == 0
    # Caduta bandierina: vince l'avversario, ma è patta se questi ha il re nudo.
    game = get_game("chess")
    chess_cls = type(game)
    normal = game.initial_state()
    assert gameplay._winner_on_time(game, normal, 0) == "o"
    assert gameplay._winner_on_time(game, normal, 1) == "x"
    bare_black = chess_cls.from_fen("7k/8/8/8/8/8/8/QK6 w - - 0 1")
    assert gameplay._winner_on_time(game, bare_black, 0) == "draw"  # al Nero resta solo il re
