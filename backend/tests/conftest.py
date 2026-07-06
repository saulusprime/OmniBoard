"""Configurazione dei test del backend.

Imposta un database SQLite temporaneo e isolato PRIMA che l'app venga importata,
così i test non toccano il database di sviluppo.
"""

import os
import tempfile
from pathlib import Path

_tmp_dir = tempfile.mkdtemp(prefix="scacchi-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp_dir) / 'test.db'}"
os.environ["ADMIN_TOKEN"] = "test-admin"
# Cache TTS isolata: i test non toccano (e non riusano) la cache di sviluppo.
os.environ["TTS_CACHE_DIR"] = str(Path(_tmp_dir) / "tts_cache")
os.environ["TTS_VOICES_DIR"] = str(Path(_tmp_dir) / "tts_voices")
# I test devono essere ermetici: neutralizza eventuali credenziali IA da un .env
# reale (il backend carica .env all'import). Con valori vuoti il seed non migra né
# attiva alcun provider, e nessun test effettua chiamate di rete.
os.environ["QWEN_API_KEY"] = ""
os.environ["DASHSCOPE_API_KEY"] = ""
# Limita il tempo del motore scacchi nei test: partite rapide, niente attese di 2s/mossa.
os.environ["AI_ENGINE_MS_MAX"] = "60"
# Nessun ritmo minimo tra le mosse IA nei test (il ritmo serve solo a chi guarda).
os.environ["AI_WATCH_PACE_MS"] = "0"
# Mosse IA sincrone nei test (deterministico: la risposta contiene già la mossa IA).
# I test dedicati alla modalità asincrona la riabilitano con monkeypatch.
os.environ["AI_ASYNC"] = "0"
