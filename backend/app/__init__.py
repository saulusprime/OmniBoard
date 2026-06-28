"""Backend FastAPI della piattaforma Scacchi."""

import sys
from pathlib import Path

# Rende importabile il pacchetto `engine` (nella root del repo) qualunque sia la
# directory di lavoro da cui si avvia il backend.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
