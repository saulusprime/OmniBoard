"""Export PGN e posizione iniziale da FEN (solo scacchi).

L'export produce tag standard + mosse in SAN (note dei giocatori come commenti
``{…}``); una partita creata da FEN riparte da lì ovunque (replay, PGN con tag
``SetUp``/``FEN``, numerazione ``1...`` se il tratto è del Nero).
"""

from app.main import app
from app.opponents.stockfish import uci_position
from fastapi.testclient import TestClient

FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]
KPK = "8/8/8/4k3/8/4K3/4P3/8 w - - 0 1"


def _user(client, alias):
    return client.post(
        "/users",
        json={"first_name": "P", "last_name": "R", "alias": alias, "email": f"{alias}@e.it"},
    ).json()


def _human_session(client, a, b, **extra):
    u1, u2 = _user(client, a), _user(client, b)
    return client.post(
        "/sessions",
        json={
            "game_code": "chess",
            "x": {"type": "human", "user_id": u1["id"]},
            "o": {"type": "human", "user_id": u2["id"]},
            **extra,
        },
    )


def test_pgn_export_full_game_with_note():
    with TestClient(app) as client:
        sid = _human_session(client, "pgn_a", "pgn_b").json()["id"]
        for uci in FOOLS_MATE:
            assert client.post(f"/sessions/{sid}/move", json={"move": uci}).status_code == 200
        client.post(f"/sessions/{sid}/note", json={"ply": 4, "text": "matto del barbiere"})
        resp = client.get(f"/sessions/{sid}/pgn")
        assert resp.status_code == 200
        assert "attachment" in resp.headers["content-disposition"]
        pgn = resp.text
        assert '[White "pgn_a"]' in pgn
        assert '[Black "pgn_b"]' in pgn
        assert '[Result "0-1"]' in pgn
        assert "1. f3 e5 2. g4 Qh4# {matto del barbiere} 0-1" in pgn
        assert "SetUp" not in pgn  # partita dalla posizione standard


def test_pgn_only_for_chess():
    with TestClient(app) as client:
        u = _user(client, "pgn_c")
        sid = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": u["id"]},
                "o": {"type": "human", "user_id": u["id"]},
            },
        ).json()["id"]
        assert client.get(f"/sessions/{sid}/pgn").status_code == 400


def test_create_from_fen_and_replay():
    with TestClient(app) as client:
        resp = _human_session(client, "fen_a", "fen_b", start_fen=KPK)
        assert resp.status_code == 201, resp.text
        view = resp.json()
        assert view["start_fen"] == KPK  # normalizzata = identica (era già canonica)
        # La moviola riparte dalla FEN: 3 pezzi in posizione, non 32.
        boards = client.get(f"/sessions/{view['id']}/replay").json()["boards"]
        assert sum(1 for cell in boards[0] if cell) == 3


def test_fen_validation_rejects_bad_positions():
    with TestClient(app) as client:
        # FEN malformata.
        assert _human_session(client, "fen_c", "fen_d", start_fen="non-una-fen").status_code == 400
        # Manca un re.
        no_king = "8/8/8/4k3/8/8/4P3/8 w - - 0 1"
        assert _human_session(client, "fen_e", "fen_f", start_fen=no_king).status_code == 400
        # Il giocatore senza il tratto (il Bianco) è sotto scacco: illegale.
        illegal = "4k3/8/8/8/8/8/8/r3K3 b - - 0 1"
        assert _human_session(client, "fen_g", "fen_h", start_fen=illegal).status_code == 400
        # FEN su un gioco che non è scacchi.
        u = _user(client, "fen_i")
        resp = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": u["id"]},
                "o": {"type": "human", "user_id": u["id"]},
                "start_fen": KPK,
            },
        )
        assert resp.status_code == 400


def test_pgn_from_fen_black_to_move():
    with TestClient(app) as client:
        fen = "4k3/7q/8/8/8/8/8/4K3 b - - 0 1"
        view = _human_session(client, "fen_j", "fen_k", start_fen=fen).json()
        # Il tratto è del Nero: muove per primo il lato O (X resta il Bianco).
        assert view["current"] == "o"
        assert client.post(f"/sessions/{view['id']}/move", json={"move": "h7h1"}).status_code == 200
        pgn = client.get(f"/sessions/{view['id']}/pgn").text
        assert '[SetUp "1"]' in pgn
        assert f'[FEN "{fen}"]' in pgn
        assert "1... Qh1+" in pgn


def test_uci_position_helper():
    assert uci_position([]) == "position startpos"
    assert uci_position(["e2e4"]) == "position startpos moves e2e4"
    assert uci_position([], KPK) == f"position fen {KPK}"
    assert uci_position(["e2e4"], KPK) == f"position fen {KPK} moves e2e4"
