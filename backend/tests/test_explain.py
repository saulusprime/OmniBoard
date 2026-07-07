"""«Spiegami questa mossa»: LLM che spiega una semimossa con i dati già prodotti."""

from app.main import app
from app.opponents import api_ai
from fastapi.testclient import TestClient

FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]


def _chess_game(client, alias_a, alias_b):
    def user(alias):
        return client.post(
            "/users",
            json={"first_name": "S", "last_name": "M", "alias": alias, "email": f"{alias}@e.it"},
        ).json()

    sid = client.post(
        "/sessions",
        json={
            "game_code": "chess",
            "x": {"type": "human", "user_id": user(alias_a)["id"]},
            "o": {"type": "human", "user_id": user(alias_b)["id"]},
        },
    ).json()["id"]
    for uci in FOOLS_MATE:
        client.post(f"/sessions/{sid}/move", json={"move": uci})
    return sid


def test_explain_requires_active_provider():
    with TestClient(app) as client:
        sid = _chess_game(client, "spia_a", "spia_b")
        resp = client.post(f"/sessions/{sid}/explain", json={"ply": 4})
        assert resp.status_code == 503  # nessun provider attivo nei test
        assert "provider" in resp.json()["detail"].lower()


def test_explain_uses_move_data_and_caches(monkeypatch):
    from app import ai_providers

    prompts = []

    def finto_llm(provider, prompt):
        prompts.append(prompt)
        return "  La donna cala in h4 e dà   scaccomatto sfruttando le case deboli.  "

    with TestClient(app) as client:
        # La partita si gioca PRIMA di attivare il finto provider: altrimenti il
        # commentatore LLM (stesso scudo guarded_complete) catturerebbe i prompt.
        sid = _chess_game(client, "spia_c", "spia_d")
        client.post(f"/sessions/{sid}/note", json={"ply": 4, "text": "che mazzata"})
        monkeypatch.setattr(api_ai, "guarded_complete", finto_llm)
        monkeypatch.setattr(
            ai_providers, "get_active_config", lambda db: {"code": "finto", "api_key": "x"}
        )

        resp = client.post(f"/sessions/{sid}/explain", json={"ply": 4})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["cached"] is False
        assert "scaccomatto" in data["text"]
        assert "  " not in data["text"]  # spazi normalizzati
        # Il prompt porta i dati GIÀ prodotti: chi muove, notazione, FEN, nota.
        prompt = prompts[0]
        assert "il Nero" in prompt
        assert "Qd8-h4#" in prompt  # la notazione del motore
        assert "FEN" in prompt
        assert "che mazzata" in prompt
        assert "non proporre di continuare" in prompt

        # Secondo clic: risposta dallo storico, il modello NON viene richiamato.
        di_nuovo = client.post(f"/sessions/{sid}/explain", json={"ply": 4})
        assert di_nuovo.json()["cached"] is True
        assert len(prompts) == 1
        # La spiegazione è persistita nello storico della mossa (vista sessione).
        view = client.get(f"/sessions/{sid}").json()
        assert "scaccomatto" in view["moves"][3]["explain"]


def test_explain_validation():
    with TestClient(app) as client:
        sid = _chess_game(client, "spia_e", "spia_f")
        assert client.post(f"/sessions/{sid}/explain", json={"ply": 99}).status_code == 400
        assert client.post("/sessions/999999/explain", json={"ply": 1}).status_code == 404
        u = client.post(
            "/users",
            json={"first_name": "S", "last_name": "M", "alias": "spia_g", "email": "sg@e.it"},
        ).json()
        tris = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": u["id"]},
                "o": {"type": "human", "user_id": u["id"]},
            },
        ).json()["id"]
        assert client.post(f"/sessions/{tris}/explain", json={"ply": 1}).status_code == 400


def test_explain_can_be_disabled(monkeypatch):
    from app import settings_service

    originale = settings_service.get

    def spento(db, key):
        return False if key == "coach.explain_enabled" else originale(db, key)

    monkeypatch.setattr(settings_service, "get", spento)
    with TestClient(app) as client:
        sid = _chess_game(client, "spia_h", "spia_i")
        assert client.post(f"/sessions/{sid}/explain", json={"ply": 1}).status_code == 403
