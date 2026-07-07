"""Riconoscimento del tilt (avviso soft + blocco opzionale) e bias cognitivi."""

from app import chess_profile, profile_cache
from app.main import app
from fastapi.testclient import TestClient

FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]  # il Bianco (X) perde in 4 semimosse
TOKEN = "test-admin"


def _user(client, alias):
    return client.post(
        "/users",
        json={"first_name": "T", "last_name": "B", "alias": alias, "email": f"{alias}@e.it"},
    ).json()


def _quick_loss(client, loser_id, winner_id):
    """Una sconfitta rapida del giocatore ``loser_id`` (matto del barbiere, 4 semimosse)."""
    sid = client.post(
        "/sessions",
        json={
            "game_code": "chess",
            "x": {"type": "human", "user_id": loser_id},
            "o": {"type": "human", "user_id": winner_id},
        },
    ).json()["id"]
    for uci in FOOLS_MATE:
        assert client.post(f"/sessions/{sid}/move", json={"move": uci}).status_code == 200
    return sid


def test_tilt_triggers_after_quick_losses():
    with TestClient(app) as client:
        u1, u2 = _user(client, "tilt_a"), _user(client, "tilt_b")
        # Due sconfitte rapide: ancora nessun tilt (soglia 3).
        for _ in range(2):
            _quick_loss(client, u1["id"], u2["id"])
        state = client.get(f"/users/{u1['id']}/tilt").json()
        assert state["tilted"] is False
        assert state["consecutive_quick_losses"] == 2

        _quick_loss(client, u1["id"], u2["id"])  # la terza fa scattare l'avviso
        state = client.get(f"/users/{u1['id']}/tilt").json()
        assert state["tilted"] is True
        assert state["consecutive_quick_losses"] == 3
        assert any("sconfitte rapide" in r for r in state["reasons"])
        assert "pausa" in state["advice"].lower()
        # Il vincitore non è in tilt.
        assert client.get(f"/users/{u2['id']}/tilt").json()["tilted"] is False
        # L'avviso è SOFT: una nuova partita si crea comunque.
        sid = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": u1["id"]},
                "o": {"type": "human", "user_id": u2["id"]},
            },
        )
        assert sid.status_code == 201


def test_tilt_block_is_admin_option():
    with TestClient(app) as client:
        u1, u2 = _user(client, "tilt_c"), _user(client, "tilt_d")
        for _ in range(3):
            _quick_loss(client, u1["id"], u2["id"])
        # Blocco attivato dall'admin: la nuova partita di scacchi è rifiutata.
        client.put(
            "/admin/settings",
            headers={"X-Admin-Token": TOKEN},
            json={"values": {"tilt.block": "true"}},
        )
        resp = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": u1["id"]},
                "o": {"type": "human", "user_id": u2["id"]},
            },
        )
        assert resp.status_code == 403
        assert "anti-tilt" in resp.json()["detail"].lower()
        # Gli altri giochi non c'entrano col tilt scacchistico.
        tris = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": u1["id"]},
                "o": {"type": "human", "user_id": u2["id"]},
            },
        )
        assert tris.status_code == 201
        client.put(
            "/admin/settings",
            headers={"X-Admin-Token": TOKEN},
            json={"values": {"tilt.block": "false"}},
        )


def test_win_resets_the_streak():
    with TestClient(app) as client:
        u1, u2 = _user(client, "tilt_e"), _user(client, "tilt_f")
        for _ in range(3):
            _quick_loss(client, u1["id"], u2["id"])
        _quick_loss(client, u2["id"], u1["id"])  # stavolta vince u1
        state = client.get(f"/users/{u1['id']}/tilt").json()
        assert state["tilted"] is False
        assert state["consecutive_losses"] == 0


def _fake_session(user_id, notations, plies_total=None, winner="o", analysis=None):
    """Sessione finta per i bias: l'utente è il lato X, ``notations`` le sue mosse."""
    import json
    from types import SimpleNamespace

    moves = []
    for i, notation in enumerate(notations):
        moves.append({"ply": 2 * i + 1, "player": "X", "notation": notation, "id": ""})
        moves.append({"ply": 2 * i + 2, "player": "O", "notation": "…", "id": ""})
    if plies_total is not None:
        while len(moves) < plies_total:
            moves.append({"ply": len(moves) + 1, "player": "O", "notation": "…", "id": ""})
    return SimpleNamespace(
        x_user_id=user_id,
        o_user_id=999,
        winner=winner,
        moves_json=json.dumps(moves),
        analysis_json=json.dumps(analysis) if analysis else None,
    )


def test_biases_detected_from_history():
    # Donna precoce in tutte le partite + arrocco mai fatto (partite lunghe).
    sessions = [
        _fake_session(7, ["e2-e4", "Qd1-h5", "Qh5xf7", "Nb1-c3", "d2-d3"], plies_total=24)
        for _ in range(6)
    ]
    biases = chess_profile._biases(sessions, 7)
    codes = {b["code"] for b in biases}
    assert "donna_precoce" in codes
    assert "re_in_centro" in codes
    donna = next(b for b in biases if b["code"] == "donna_precoce")
    assert donna["share"] == 1.0 and donna["games"] == 6


def test_bias_capture_blunders_and_monotony():
    # Monotonia: il cavallo balla per 4 delle prime 8 mosse proprie.
    monotone = ["Nb1-c3", "Nc3-e4", "Ne4-g5", "Ng5-f3", "e2-e4", "d2-d4", "a2-a3", "b2-b3"]
    # Coazione alla cattura: i blunder (??) dell'analisi sono tutti catture.
    analysis = {
        "status": "done",
        "evals": [
            {"ply": 1, "by": "x", "tag": "??", "loss": 300},
            {"ply": 3, "by": "x", "tag": "??", "loss": 250},
            {"ply": 5, "by": "x", "tag": "??", "loss": 400},
        ],
    }
    capture_moves = ["Qd1xh5", "Rf1xf7", "Nb1xc3", "d2-d4", "e2-e4", "f2-f3", "g2-g3", "h2-h3"]
    sessions = [_fake_session(7, monotone, plies_total=24) for _ in range(5)] + [
        _fake_session(7, capture_moves, plies_total=24, analysis=analysis)
    ]
    biases = chess_profile._biases(sessions, 7)
    codes = {b["code"] for b in biases}
    assert "monotonia_apertura" in codes
    assert "coazione_cattura" in codes
    cattura = next(b for b in biases if b["code"] == "coazione_cattura")
    assert cattura["share"] == 1.0


def test_biases_need_a_sample():
    # Sotto il campione minimo (5 partite) nessun bias dichiarato.
    sessions = [_fake_session(7, ["Qd1-h5", "e2-e4"], plies_total=24) for _ in range(3)]
    assert chess_profile._biases(sessions, 7) == []


def test_profile_exposes_biases():
    with TestClient(app) as client:
        u1, u2 = _user(client, "tilt_g"), _user(client, "tilt_h")
        for _ in range(5):
            _quick_loss(client, u1["id"], u2["id"])
        profile_cache.invalidate(u1["id"])
        profile = client.get(f"/users/{u1['id']}/chess-profile").json()
        assert "biases" in profile  # la chiave c'è (lista, anche vuota)
        assert isinstance(profile["biases"], list)
