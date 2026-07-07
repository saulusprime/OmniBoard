"""Circuit breaker per i provider IA remoti.

Dopo N errori CONSECUTIVI (rete, timeout, quota) il circuito del provider si
APRE: per un periodo di raffreddamento le chiamate remote vengono saltate del
tutto (la partita usa subito il giocatore locale, senza aspettare il timeout a
ogni mossa). Scaduto il raffreddamento il circuito è MEZZO APERTO: la prossima
chiamata fa da sonda — se riesce il circuito si richiude, se fallisce si riapre
per un altro giro. Un successo qualsiasi azzera il conteggio.

Stato in memoria per processo (niente DB: è protezione runtime, non cronologia);
le soglie arrivano dalla configurazione del provider (``ai_providers.get_config``
le inietta dai parametri ``providers.breaker_*``). Il pulsante «Verifica
connessione» della pagina Provider IA chiama il provider SENZA passare dal
breaker e ne registra l'esito: è la sonda manuale naturale.
"""

from __future__ import annotations

import threading
import time

DEFAULT_FAILURES = 3  # errori consecutivi che aprono il circuito
DEFAULT_COOLDOWN_S = 120  # raffreddamento prima della sonda

_lock = threading.Lock()
# {code: {"failures": int, "opened_at": float | None}}
_state: dict[str, dict] = {}


def _entry(code: str) -> dict:
    return _state.setdefault(code, {"failures": 0, "opened_at": None})


def allow(code: str, cooldown_s: int = DEFAULT_COOLDOWN_S) -> bool:
    """La chiamata remota può partire? False = circuito aperto, si salta."""
    with _lock:
        entry = _entry(code)
        if entry["opened_at"] is None:
            return True
        if time.monotonic() - entry["opened_at"] >= cooldown_s:
            return True  # mezzo aperto: questa chiamata fa da sonda
        return False


def record_success(code: str) -> None:
    with _lock:
        _state[code] = {"failures": 0, "opened_at": None}


def record_failure(
    code: str, max_failures: int = DEFAULT_FAILURES, cooldown_s: int = DEFAULT_COOLDOWN_S
) -> None:
    """Registra un errore; al raggiungimento della soglia apre (o riapre) il circuito."""
    with _lock:
        entry = _entry(code)
        entry["failures"] += 1
        if entry["failures"] >= max_failures:
            entry["opened_at"] = time.monotonic()


def snapshot(code: str, cooldown_s: int = DEFAULT_COOLDOWN_S) -> dict:
    """Stato leggibile per la pagina Provider IA."""
    with _lock:
        entry = _entry(code)
        if entry["opened_at"] is None:
            return {"open": False, "failures": entry["failures"], "retry_in_s": 0}
        remaining = cooldown_s - (time.monotonic() - entry["opened_at"])
        return {
            "open": remaining > 0,
            "failures": entry["failures"],
            "retry_in_s": max(0, int(remaining)),
        }


def reset(code: str | None = None) -> None:
    """Azzera lo stato (tutti i provider se code è None). Usata nei test."""
    with _lock:
        if code is None:
            _state.clear()
        else:
            _state.pop(code, None)
