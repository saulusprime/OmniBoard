"""Watch party: i PRONOSTICI degli spettatori sulla prossima mossa.

Ogni spettatore di una diretta può cliccare una casella del tavoliere:
«la prossima mossa finisce qui». I voti si aggregano in una HEATMAP mostrata
a tutti gli spettatori. Sono pronostici effimeri legati alla POSIZIONE
corrente (la semimossa): quando la mossa vera arriva, i voti ripartono da
zero per la posizione nuova.

Stato IN MEMORIA per processo (come il circuit breaker): i pronostici sono
volatili per natura — perderli a un riavvio non toglie nulla. Un voto per
spettatore per posizione (rivotare sposta il voto); lo spettatore è
identificato dall'id utente se loggato, altrimenti da una chiave anonima
generata dal client (localStorage). Nessun gettone in palio, per ora: la
valuta virtuale è pronta, il collegamento è un passo futuro.
"""

from __future__ import annotations

import threading
import time

_lock = threading.Lock()
# {session_id: {"ply": int, "votes": {voter_key: cell}, "updated": monotonic}}
_store: dict[int, dict] = {}
_MAX_SESSIONS = 200  # tetto di memoria: oltre, si potano le sessioni più vecchie


def _prune_locked() -> None:
    if len(_store) <= _MAX_SESSIONS:
        return
    for sid, _entry in sorted(_store.items(), key=lambda kv: kv[1]["updated"])[
        : len(_store) - _MAX_SESSIONS
    ]:
        _store.pop(sid, None)


def vote(session_id: int, current_ply: int, claimed_ply: int, voter: str, cell: int) -> bool:
    """Registra (o sposta) il pronostico del voter.

    ``current_ply`` è la verità della sessione (dal DB): un voto che dichiara
    una posizione diversa è STANTIO (la mossa è già arrivata) e si scarta.
    """
    if claimed_ply != current_ply:
        return False
    with _lock:
        entry = _store.get(session_id)
        if entry is None or entry["ply"] != current_ply:
            # Posizione nuova (o prima visita): i voti vecchi non valgono più.
            entry = {"ply": current_ply, "votes": {}, "updated": time.monotonic()}
            _store[session_id] = entry
            _prune_locked()
        entry["votes"][voter] = cell
        entry["updated"] = time.monotonic()
        return True


def aggregate(session_id: int, ply: int) -> dict:
    """I pronostici per la posizione corrente: {ply, total, cells: {cell: n}}."""
    with _lock:
        entry = _store.get(session_id)
        if entry is None or entry["ply"] != ply:
            return {"ply": ply, "total": 0, "cells": {}}
        cells: dict[int, int] = {}
        for cell in entry["votes"].values():
            cells[cell] = cells.get(cell, 0) + 1
        return {"ply": ply, "total": len(entry["votes"]), "cells": cells}


def drop(session_id: int) -> None:
    """Partita finita: i pronostici non servono più."""
    with _lock:
        _store.pop(session_id, None)
