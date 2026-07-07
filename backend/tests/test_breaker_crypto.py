"""Circuit breaker dei provider remoti e cifratura dei token a riposo."""

from app import ai_providers, breaker, token_crypto
from app.database import SessionLocal
from app.main import app
from app.models import AiProvider
from app.opponents import api_ai
from fastapi.testclient import TestClient

from engine import get_game

TOKEN = "test-admin"


# ----- Cifratura -----
def test_token_crypto_roundtrip(monkeypatch):
    stored = token_crypto.encrypt("sk-segretissimo")
    assert token_crypto.is_encrypted(stored)
    assert "sk-segretissimo" not in stored
    assert token_crypto.decrypt(stored) == "sk-segretissimo"
    # Un valore legacy in chiaro passa com'è (verrà cifrato dal seed).
    assert token_crypto.decrypt("sk-in-chiaro") == "sk-in-chiaro"
    assert token_crypto.decrypt(None) is None
    # Chiave cambiata: il token cifrato non è più leggibile (None, mai eccezioni).
    monkeypatch.setenv("TOKENS_KEY", token_crypto.Fernet.generate_key().decode())
    assert token_crypto.decrypt(stored) is None


def test_update_stores_encrypted_and_config_decrypts():
    with TestClient(app) as client:
        resp = client.put(
            "/admin/ai-providers",
            headers={"X-Admin-Token": TOKEN},
            json={"providers": {"grok": {"api_key": "xai-chiave-prova"}}},
        )
        assert resp.status_code == 200
        db = SessionLocal()
        try:
            row = db.get(AiProvider, "grok")
            # Nel DB non c'è MAI il token in chiaro.
            assert token_crypto.is_encrypted(row.api_key)
            assert "xai-chiave-prova" not in row.api_key
            cfg = ai_providers.get_config(db, "grok")
            assert cfg["api_key"] == "xai-chiave-prova"
            # La config porta anche le soglie del breaker (per api_ai, senza DB).
            assert cfg["breaker_failures"] == 3
            assert cfg["breaker_cooldown_s"] == 120
            db.get(AiProvider, "grok").api_key = None  # pulizia: ordine test casuale
            db.commit()
        finally:
            db.close()


def test_seed_encrypts_legacy_plaintext_rows():
    with TestClient(app):  # l'avvio dell'app esegue il seed
        db = SessionLocal()
        try:
            row = db.get(AiProvider, "openai")
            row.api_key = "sk-legacy-in-chiaro"  # scaffold pre-cifratura
            db.commit()
            ai_providers.seed_providers(db)  # migrazione lazy al riavvio
            db.refresh(row)
            assert token_crypto.is_encrypted(row.api_key)
            assert ai_providers.get_config(db, "openai")["api_key"] == "sk-legacy-in-chiaro"
            row.api_key = None  # pulizia: non lasciare token allo stato successivo
            db.commit()
        finally:
            db.close()


def test_unreadable_token_is_flagged(monkeypatch):
    with TestClient(app) as client:
        client.put(
            "/admin/ai-providers",
            headers={"X-Admin-Token": TOKEN},
            json={"providers": {"gemini": {"api_key": "AIza-prova"}}},
        )
        monkeypatch.setenv("TOKENS_KEY", token_crypto.Fernet.generate_key().decode())
        db = SessionLocal()
        try:
            # Con la chiave cambiata il token non si decifra: config assente...
            assert ai_providers.get_config(db, "gemini") is None
            listed = next(p for p in ai_providers.list_providers(db) if p["code"] == "gemini")
            # ...ma la lista segnala che c'è un token da reinserire.
            assert listed["has_key"] is True
            assert listed["key_unreadable"] is True
            db.get(AiProvider, "gemini").api_key = None  # pulizia: ordine test casuale
            db.commit()
        finally:
            db.close()


# ----- Circuit breaker -----
def test_breaker_opens_after_failures_and_half_opens():
    breaker.reset("prova")
    assert breaker.allow("prova") is True
    breaker.record_failure("prova", max_failures=3, cooldown_s=60)
    breaker.record_failure("prova", max_failures=3, cooldown_s=60)
    assert breaker.allow("prova") is True  # sotto soglia: circuito chiuso
    breaker.record_failure("prova", max_failures=3, cooldown_s=60)
    assert breaker.allow("prova", cooldown_s=60) is False  # aperto
    snap = breaker.snapshot("prova", cooldown_s=60)
    assert snap["open"] is True and 0 < snap["retry_in_s"] <= 60
    # Raffreddamento scaduto (cooldown 0): mezzo aperto, la chiamata fa da sonda.
    assert breaker.allow("prova", cooldown_s=0) is True
    # Sonda fallita: si riapre SUBITO (il conteggio è già oltre soglia).
    breaker.record_failure("prova", max_failures=3, cooldown_s=60)
    assert breaker.allow("prova", cooldown_s=60) is False
    # Un successo richiude e azzera tutto.
    breaker.record_success("prova")
    assert breaker.allow("prova") is True
    assert breaker.snapshot("prova")["failures"] == 0
    breaker.reset("prova")


def test_guarded_complete_skips_calls_when_open(monkeypatch):
    breaker.reset("finto")
    calls = {"n": 0}

    def sempre_giu(provider, prompt):
        calls["n"] += 1
        raise RuntimeError("rete giù")

    monkeypatch.setattr(api_ai, "_complete", sempre_giu)
    cfg = {"code": "finto", "breaker_failures": 3, "breaker_cooldown_s": 300}
    for _ in range(5):
        assert api_ai.guarded_complete(cfg, "ciao") is None
    # Dopo i 3 errori il circuito è aperto: le ultime chiamate NON toccano la rete.
    assert calls["n"] == 3
    # remote_move passa dallo stesso scudo: nessuna nuova chiamata.
    game = get_game("tictactoe")
    state = game.initial_state()
    assert api_ai.remote_move(game, state, list(game.legal_moves(state)), cfg) is None
    assert calls["n"] == 3

    # Il provider torna su: la sonda (cooldown azzerato) richiude il circuito.
    def torna_su(provider, prompt):
        calls["n"] += 1
        return "ok"

    monkeypatch.setattr(api_ai, "_complete", torna_su)
    cfg_pronto = dict(cfg, breaker_cooldown_s=0)
    assert api_ai.guarded_complete(cfg_pronto, "ciao") == "ok"
    assert calls["n"] == 4
    assert breaker.snapshot("finto")["open"] is False
    breaker.reset("finto")
