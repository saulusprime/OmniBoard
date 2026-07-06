"""Test del servizio TTS multi-motore (gestione lingue, cache, degradazione).

I motori reali NON vengono usati: si inietta un motore finto nel registro
``tts.ENGINES`` (i modelli veri scaricherebbero da HuggingFace). Qui si prova
il CONTRATTO: routing per lingua, cache su disco, validazioni, 503 spiegati.
"""

import wave

from app import tts
from app.main import app
from fastapi.testclient import TestClient

TOKEN = "test-admin"  # impostato in conftest tramite ADMIN_TOKEN


def _fake_engine(calls):
    """Motore finto: scrive un WAV valido e conta le sintesi effettive."""

    def synth(text, voice, speed, out_path):
        calls.append((text, voice, speed))
        with wave.open(str(out_path), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(24000)
            f.writeframes(b"\x00\x00" * 240)

    return synth


def test_language_routing_and_disk_cache(monkeypatch):
    calls_it, calls_en = [], []
    monkeypatch.setitem(tts.ENGINES, "piper", _fake_engine(calls_it))
    monkeypatch.setitem(tts.ENGINES, "kitten", _fake_engine(calls_en))
    with TestClient(app) as client:
        # Italiano → Piper (voce di default it_IT-paola-medium).
        r = client.get("/tts", params={"text": "Benvenuto nella lezione", "lang": "it"})
        assert r.status_code == 200 and r.headers["content-type"].startswith("audio/wav")
        assert len(calls_it) == 1 and calls_it[0][1] == "it_IT-paola-medium"
        # Inglese → KittenTTS (voce di default expr-voice-2-f).
        client.get("/tts", params={"text": "Welcome to the lesson", "lang": "en"})
        assert len(calls_en) == 1 and calls_en[0][1] == "expr-voice-2-f"
        # Stessa frase italiana di nuovo: servita dalla CACHE, nessuna nuova sintesi
        # (gli spazi vengono normalizzati: la chiave di cache è stabile).
        again = client.get("/tts", params={"text": "  Benvenuto   nella lezione ", "lang": "it"})
        assert again.status_code == 200
        assert len(calls_it) == 1
        # Lingua di default (it) quando lang è omessa.
        client.get("/tts", params={"text": "Frase nuova"})
        assert len(calls_it) == 2


def test_validation_errors(monkeypatch):
    monkeypatch.setitem(tts.ENGINES, "piper", _fake_engine([]))
    with TestClient(app) as client:
        assert client.get("/tts", params={"text": ""}).status_code == 400
        r = client.get("/tts", params={"text": "ciao", "lang": "fr"})
        assert r.status_code == 400
        assert "non supportata" in r.json()["detail"]
        troppo = client.get("/tts", params={"text": "x" * 1000, "lang": "it"})
        assert troppo.status_code == 400
        assert "troppo lungo" in troppo.json()["detail"]


def test_disabled_and_engine_failure(monkeypatch):
    with TestClient(app) as client:
        # Interruttore del super admin: servizio spento → 503.
        client.put(
            "/admin/settings",
            json={"values": {"tts.enabled": "false"}},
            headers={"X-Admin-Token": TOKEN},
        )
        assert client.get("/tts", params={"text": "ciao", "lang": "it"}).status_code == 503
        client.put(
            "/admin/settings",
            json={"values": {"tts.enabled": "true"}},
            headers={"X-Admin-Token": TOKEN},
        )

        # Motore che esplode → 503 con dettaglio, e nessun file sporco in cache.
        def broken(text, voice, speed, out_path):
            raise RuntimeError("modello mancante")

        monkeypatch.setitem(tts.ENGINES, "piper", broken)
        r = client.get("/tts", params={"text": "frase mai sintetizzata prima", "lang": "it"})
        assert r.status_code == 503
        assert "modello mancante" in r.json()["detail"]
        assert not list(tts.cache_dir().glob("*.tmp.wav"))


def test_status_reports_languages_and_cache():
    with TestClient(app) as client:
        data = client.get("/tts/status").json()
        assert data["enabled"] is True
        assert set(data["langs"]) == {"it", "en"}
        assert data["langs"]["it"]["engine"] == "piper"
        assert data["langs"]["en"]["engine"] == "kitten"
        # kitten e piper sono installati nel venv di sviluppo: disponibili
        # (i modelli/voci si scaricano solo al primo uso reale).
        assert data["langs"]["en"]["available"] is True
        assert "cache" in data and data["cache"]["files"] >= 0
