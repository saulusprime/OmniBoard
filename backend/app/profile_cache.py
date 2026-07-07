"""Cache in memoria del profilo avversario (``chess_profile.build_profile``).

Il profilo guida lo stile dell'IA e viene consultato a OGNI mossa dell'IA nelle
partite umano-vs-IA; ricostruirlo ogni volta significa rileggere fino a 200
sessioni e le loro analisi. Qui si tiene l'ultima copia per giocatore con:

- **invalidazione a eventi** — il profilo cambia solo quando finisce una partita
  di scacchi del giocatore (``services.finalize_session``) o quando un'analisi
  post-partita viene scritta (``analysis``): quei punti chiamano
  :func:`invalidate`;
- **TTL di sicurezza** (``profile.cache_ttl_s``, default 300s; 0 = cache
  disattivata) per coprire ogni percorso di scrittura non previsto.

Il dict restituito è CONDIVISO tra i chiamanti: va trattato come immutabile
(chi lo adatta ne copia i pezzi, come fa ``opponent_style``). Stato per
processo, protetto da lock (worker IA e richieste girano su thread diversi).
"""

from __future__ import annotations

import threading
import time

from . import chess_profile, settings_service

_lock = threading.Lock()
# {user_id: (profile, monotonic dell'istante di costruzione)}
_store: dict[int, tuple[dict | None, float]] = {}


def get(db, user_id: int) -> dict | None:
    """Profilo del giocatore, dalla cache se fresco (altrimenti ricostruito)."""
    ttl = int(settings_service.get(db, "profile.cache_ttl_s"))
    if ttl > 0:
        with _lock:
            entry = _store.get(user_id)
        if entry is not None and time.monotonic() - entry[1] < ttl:
            return entry[0]
    profile = chess_profile.build_profile(db, user_id)
    if ttl > 0:
        with _lock:
            _store[user_id] = (profile, time.monotonic())
    return profile


def invalidate(user_id: int | None = None) -> None:
    """Butta la voce del giocatore (o tutte con None): al prossimo uso si ricostruisce."""
    with _lock:
        if user_id is None:
            _store.clear()
        else:
            _store.pop(user_id, None)
