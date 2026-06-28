"""Test dei provider IA configurabili e dell'interfaccia super admin (senza rete)."""

from app import ai_providers
from app.database import Base
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TOKEN = "test-admin"  # impostato in conftest tramite ADMIN_TOKEN


def _fresh_session():
    """Sessione su un DB SQLite in memoria, isolata dall'app (per testare il seed)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


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


def test_seed_migrates_qwen_from_env_and_activates(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("QWEN_API_KEY", "sk-env-123")
    monkeypatch.setenv("QWEN_BASE_URL", "https://example.test/compatible-mode/v1")
    monkeypatch.setenv("QWEN_MODEL", "qwen-test")
    db = _fresh_session()
    try:
        ai_providers.seed_providers(db)
        cfg = ai_providers.get_active_config(db)  # qwen attivato in automatico
        assert cfg is not None
        assert cfg["code"] == "qwen"
        assert cfg["api_key"] == "sk-env-123"
        assert cfg["base_url"] == "https://example.test/compatible-mode/v1"
        assert cfg["model"] == "qwen-test"
        listed = next(p for p in ai_providers.list_providers(db) if p["code"] == "qwen")
        assert listed["has_key"] is True
        assert "api_key" not in listed  # il token non trapela
    finally:
        db.close()


def test_seed_backfills_existing_keyless_qwen(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("QWEN_API_KEY", "")
    db = _fresh_session()
    try:
        ai_providers.seed_providers(db)  # senza token: nessun provider attivo
        assert ai_providers.get_active_config(db) is None
        monkeypatch.setenv("QWEN_API_KEY", "sk-late")  # il token arriva dopo
        ai_providers.seed_providers(db)  # backfill su riga esistente + attivazione
        cfg = ai_providers.get_active_config(db)
        assert cfg is not None
        assert cfg["api_key"] == "sk-late"
    finally:
        db.close()


def test_seed_does_not_override_user_choice(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("QWEN_API_KEY", "sk-1")
    db = _fresh_session()
    try:
        ai_providers.seed_providers(db)  # attiva qwen
        ai_providers.update_providers(db, active="", providers={})  # l'utente disattiva
        assert ai_providers.get_active_config(db) is None
        ai_providers.seed_providers(db)  # un riavvio non deve riattivare (token già presente)
        assert ai_providers.get_active_config(db) is None
    finally:
        db.close()
