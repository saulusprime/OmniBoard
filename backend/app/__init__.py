"""Backend FastAPI della piattaforma Scacchi."""

import sys
from pathlib import Path

from dotenv import load_dotenv

# Rende importabile il pacchetto `engine` (nella root del repo) qualunque sia la
# directory di lavoro da cui si avvia il backend.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Carica le variabili dal file .env nella root del repo (come fa il frontend).
# Va eseguito qui, prima di ogni altro import del pacchetto, perché i moduli
# leggono os.getenv all'import (es. DATABASE_URL, QWEN_*). Non sovrascrive le
# variabili già presenti nell'ambiente (override=False), così i test restano isolati.
load_dotenv(_REPO_ROOT / ".env")
