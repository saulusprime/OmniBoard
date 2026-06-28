"""Test dei provider IA configurabili e dell'interfaccia super admin (senza rete)."""

from app.main import app
from fastapi.testclient import TestClient

TOKEN = "test-admin"  # impostato in conftest tramite ADMIN_TOKEN


def test_providers_seeded_and_no_key_leak():
    with TestClient(app) as client:
        data = client.get("/admin/ai-providers").json()
        codes = {p["code"] for p in data["providers"]}
        assert {"qwen", "anthropic", "openai"} <= codes
        for p in data["providers"]:
            assert "api_key" not in p  # il token non è mai esposto
            assert "has_key" in p
        assert data["active"] == ""


def test_update_requires_token():
    with TestClient(app) as client:
        no_token = client.put("/admin/ai-providers", json={"active": "qwen", "providers": {}})
        assert no_token.status_code == 401


def test_update_sets_key_and_active_without_leak():
    with TestClient(app) as client:
        try:
            resp = client.put(
                "/admin/ai-providers",
                headers={"X-Admin-Token": TOKEN},
                json={
                    "active": "qwen",
                    "providers": {
                        "qwen": {
                            "base_url": "https://example.test/v1",
                            "model": "qwen-x",
                            "api_key": "sk-fake",
                        }
                    },
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["active"] == "qwen"
            qwen = next(p for p in data["providers"] if p["code"] == "qwen")
            assert qwen["has_key"] is True
            assert qwen["base_url"] == "https://example.test/v1"
            assert qwen["model"] == "qwen-x"
            assert "api_key" not in qwen
        finally:
            # Ripristina "nessun provider attivo" per non innescare chiamate di rete altrove.
            client.put(
                "/admin/ai-providers",
                headers={"X-Admin-Token": TOKEN},
                json={"active": "", "providers": {}},
            )


def test_test_endpoint_reports_missing_key():
    with TestClient(app) as client:
        result = client.post(
            "/admin/ai-providers/anthropic/test", headers={"X-Admin-Token": TOKEN}
        ).json()
        assert result["ok"] is False  # nessun token configurato in test → niente rete
