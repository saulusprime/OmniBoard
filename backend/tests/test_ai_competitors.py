"""Test dei concorrenti IA multipli: un provider per lato, scelto al setup.

Nei test nessun provider ha un token (conftest neutralizza le chiavi), quindi
le mosse ripiegano sul giocatore locale: qui si verifica il MODELLO (catalogo,
validazione, persistenza per lato, esposizione in vista), non la rete.
"""

from app.main import app
from fastapi.testclient import TestClient


def test_catalog_includes_gemini_and_grok():
    with TestClient(app) as client:
        data = client.get("/admin/ai-providers").json()
        codes = {p["code"] for p in data["providers"]}
        assert {"qwen", "anthropic", "openai", "gemini", "grok"} <= codes
        gemini = next(p for p in data["providers"] if p["code"] == "gemini")
        assert gemini["label"] == "Gemini (Google)"
        assert "api_key" not in gemini  # mai esposto: solo has_key
        assert gemini["has_key"] is False


def test_session_with_per_side_competitors():
    with TestClient(app) as client:
        session = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "ai", "provider": "anthropic"},
                "o": {"type": "ai", "provider": "gemini"},
            },
        ).json()
        # Ogni lato espone il SUO concorrente, con l'etichetta per l'interfaccia.
        assert session["players"]["x"]["provider"] == "anthropic"
        assert session["players"]["x"]["provider_label"] == "Claude (Anthropic)"
        assert session["players"]["o"]["provider"] == "gemini"
        assert session["players"]["o"]["provider_label"] == "Gemini (Google)"
        # Senza token la partita avanza comunque (ripiego sul giocatore locale).
        final = client.get(f"/sessions/{session['id']}").json()
        assert final["status"] in {"in_progress", "finished"}
        assert final["last_ai"] is None or final["last_ai"]["source"] in {"book", "local", "engine"}


def test_unknown_competitor_is_rejected():
    with TestClient(app) as client:
        resp = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "ai", "provider": "skynet"},
                "o": {"type": "ai"},
            },
        )
        assert resp.status_code == 400
        assert "Provider IA sconosciuto" in resp.json()["detail"]


def test_provider_none_keeps_historic_behaviour():
    with TestClient(app) as client:
        session = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "ai"},
                "o": {"type": "ai"},
            },
        ).json()
        assert session["players"]["x"]["provider"] is None
        assert session["players"]["x"]["provider_label"] is None
