"""Test di moviola (replay), note nello storico, analisi post-partita, GIF e sparring.

Partita-cavia: il «matto dell'imbecille» (1.f3 e5 2.g4 Dh4#), la partita di
scacchi più corta possibile — 4 semimosse e uno stato finale vero. Stockfish è
un finto motore interattivo che risponde valutazioni fisse (nessun binario reale).
"""

import itertools

from app.main import app
from app.opponents import stockfish
from fastapi.testclient import TestClient

TOKEN = "test-admin"  # impostato in conftest tramite ADMIN_TOKEN

FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]


_SEQ = itertools.count(1)


def _fools_mate(client):
    n = next(_SEQ)  # alias unici: il DB dei test è condiviso tra i test del file
    users = []
    for tag in ("a", "b"):
        users.append(
            client.post(
                "/users",
                json={
                    "first_name": "P",
                    "last_name": "R",
                    "alias": f"replay_{tag}{n}",
                    "email": f"replay_{tag}{n}@e.it",
                },
            ).json()
        )
    session = client.post(
        "/sessions",
        json={
            "game_code": "chess",
            "x": {"type": "human", "user_id": users[0]["id"]},
            "o": {"type": "human", "user_id": users[1]["id"]},
        },
    )
    sid = session.json()["id"]
    for uci in FOOLS_MATE:
        resp = client.post(f"/sessions/{sid}/move", json={"move": uci})
        assert resp.status_code == 200, resp.text
    final = client.get(f"/sessions/{sid}").json()
    assert final["status"] == "finished" and final["winner"] == "o"
    return sid


def _fake_analyser(tmp_path):
    """Finto Stockfish interattivo che valuta sempre +42 cp e propone e2e4."""
    fake = tmp_path / "fakefish"
    fake.write_text(
        "#!/bin/sh\n"
        "while read line; do\n"
        '  case "$line" in\n'
        "    uci) echo 'id name Fakefish'; echo 'uciok';;\n"
        "    go*) echo 'info depth 8 score cp 42 pv e2e4'; echo 'bestmove e2e4';;\n"
        "    quit) exit 0;;\n"
        "  esac\n"
        "done\n"
    )
    fake.chmod(0o755)
    return str(fake)


def test_replay_returns_every_position():
    with TestClient(app) as client:
        sid = _fools_mate(client)
        replay = client.get(f"/sessions/{sid}/replay").json()
        assert len(replay["boards"]) == 5  # iniziale + 4 semimosse
        assert replay["boards"][0].count("♙") == 8  # posizione iniziale intatta
        assert "♛" in replay["boards"][4]  # la donna nera è arrivata in h4


def test_notes_live_inside_the_move_log():
    with TestClient(app) as client:
        sid = _fools_mate(client)
        out = client.post(f"/sessions/{sid}/note", json={"ply": 4, "text": "Scacco matto!"})
        assert out.status_code == 200 and out.json()["note"] == "Scacco matto!"
        moves = client.get(f"/sessions/{sid}").json()["moves"]
        assert moves[3]["note"] == "Scacco matto!"  # la nota vive nello storico
        # Nota vuota = cancellazione; semimossa inesistente = 400.
        client.post(f"/sessions/{sid}/note", json={"ply": 4, "text": " "})
        assert "note" not in client.get(f"/sessions/{sid}").json()["moves"][3]
        missing = client.post(f"/sessions/{sid}/note", json={"ply": 99, "text": "x"})
        assert missing.status_code == 400


def test_analysis_tags_and_persistence(tmp_path, monkeypatch):
    fake = _fake_analyser(tmp_path)
    with TestClient(app) as client:
        client.put(
            "/admin/settings",
            json={"values": {"stockfish.path": fake, "stockfish.analysis_ms": "60"}},
            headers={"X-Admin-Token": TOKEN},
        )
        sid = _fools_mate(client)
        # Partita in corso o gioco sbagliato → rifiuti chiari (409/400) già coperti
        # dal flusso: qui si analizza la partita conclusa (sincrono con AI_ASYNC=0).
        started = client.post(f"/sessions/{sid}/analysis")
        assert started.status_code == 202 and started.json()["started"] is True
        result = client.get(f"/sessions/{sid}/analysis").json()
        assert result["status"] == "done"
        assert len(result["evals"]) == 4
        first = result["evals"][0]
        assert {"ply", "by", "cp", "loss", "tag", "best"} <= set(first)
        # Una seconda richiesta NON rifà il lavoro (risultato in analysis_json).
        again = client.post(f"/sessions/{sid}/analysis").json()
        assert again["already_done"] is True
        client.put(
            "/admin/settings",
            json={"values": {"stockfish.path": "", "stockfish.analysis_ms": "200"}},
            headers={"X-Admin-Token": TOKEN},
        )


def test_gif_export_is_a_real_gif():
    with TestClient(app) as client:
        sid = _fools_mate(client)
        resp = client.get(f"/sessions/{sid}/gif")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/gif"
        assert resp.content[:6] in (b"GIF89a", b"GIF87a")
        assert len(resp.content) > 1000  # 5 fotogrammi veri, non un placeholder


def test_sparring_estimates_elo(tmp_path):
    fake = _fake_analyser(tmp_path)  # gioca e2e4 sempre: presto illegale → patte
    with TestClient(app) as client:
        client.put(
            "/admin/settings",
            json={"values": {"stockfish.path": fake}},
            headers={"X-Admin-Token": TOKEN},
        )
        # Zeus non è misurabile (nessun Elo simulato); serve il token admin.
        assert client.post("/admin/sparring", json={"level": "zeus", "games": 1}).status_code == 401
        bad = client.post(
            "/admin/sparring",
            json={"level": "zeus", "games": 1},
            headers={"X-Admin-Token": TOKEN},
        )
        assert bad.status_code == 409
        ok = client.post(
            "/admin/sparring",
            json={"level": "hermes", "games": 2, "engine_ms": 60},
            headers={"X-Admin-Token": TOKEN},
        )
        assert ok.status_code == 200, ok.text
        state = client.get("/admin/sparring").json()
        assert state["status"] == "done" and len(state["games"]) == 2
        # Il finto motore pareggia sempre → stima = Elo del preset (1700).
        assert state["elo_estimate"] == 1700
        assert state["elo_margin"] > 0
        client.put(
            "/admin/settings",
            json={"values": {"stockfish.path": ""}},
            headers={"X-Admin-Token": TOKEN},
        )
        stockfish.shutdown()
