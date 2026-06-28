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
