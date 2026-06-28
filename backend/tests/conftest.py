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
# I test devono essere ermetici: neutralizza eventuali credenziali IA da un .env
# reale (il backend carica .env all'import). Con valori vuoti il seed non migra né
# attiva alcun provider, e nessun test effettua chiamate di rete.
os.environ["QWEN_API_KEY"] = ""
os.environ["DASHSCOPE_API_KEY"] = ""
