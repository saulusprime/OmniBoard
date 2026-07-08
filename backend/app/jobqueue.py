"""Coda di lavoro delle mosse IA: pool di worker LIMITATO, in-process.

Sostituisce il thread-per-sessione di ``gameplay``: prima N partite IA
simultanee aprivano N thread di motore in concorrenza per la CPU; ora i job
passano da una coda servita da ``ai.workers`` thread (default 2) — le partite
in eccesso ASPETTANO il loro turno invece di degradare tutte insieme.

Perché NON un broker esterno (RabbitMQ & co.), valutato e scartato:

- il **DB è già lo stato durevole** dei job — una sessione ``in_progress`` col
  tratto all'IA È il lavoro pendente; :func:`recovery_scan` lo ricostruisce al
  riavvio (un broker sarebbe una seconda fonte di verità da riconciliare);
- l'app è un processo singolo su SQLite: broker + consumer + serializzazione
  sono footprint operativo senza guadagno a questa scala;
- quando si passerà a più processi/host (e a Postgres), il candidato naturale
  è una coda su Postgres (``SELECT … FOR UPDATE SKIP LOCKED``) o Redis/RQ —
  questo modulo è l'interfaccia dietro cui infilarla (``enqueue``/``snapshot``
  restano, cambia il trasporto).

Semantica: ``enqueue`` è idempotente (una sessione già in coda o in lavorazione
non si duplica — il polling dei client non genera tempeste); i worker chiamano
``gameplay.advance_ai`` con una sessione DB propria; gli errori incrementano un
contatore e NON abbattono il worker (la partita resta al turno dell'IA: il
prossimo GET la ri-accoda — auto-ripristino invariato). Con ``AI_ASYNC=0`` la
coda non parte mai: i test restano sincroni e deterministici.
"""

from __future__ import annotations

import logging
import queue
import threading

from engine import get_game

from . import models
from .database import SessionLocal

logger = logging.getLogger(__name__)

DEFAULT_WORKERS = 2

_lock = threading.Lock()
_queue: queue.Queue[int] = queue.Queue()
_pending: set[int] = set()  # in coda, non ancora presi in carico
_active: set[int] = set()  # in lavorazione da un worker
_threads: list[threading.Thread] = []
_counters = {"done": 0, "errors": 0}


def _default_process(session_id: int) -> None:
    """Esegue le mosse IA della sessione (corpo del job; iniettabile nei test)."""
    from . import gameplay  # import locale: gameplay importa questo modulo

    db = SessionLocal()
    try:
        session = db.get(models.GameSession, session_id)
        if session and session.status == "in_progress":
            gameplay.advance_ai(db, get_game(session.game.code), session)
    finally:
        db.close()


_process = _default_process  # monkeypatchabile (test del cap di concorrenza)


def _worker_loop() -> None:
    while True:
        session_id = _queue.get()
        with _lock:
            _pending.discard(session_id)
            _active.add(session_id)
        try:
            _process(session_id)
            with _lock:
                _counters["done"] += 1
        except Exception:  # noqa: BLE001 - un job rotto non abbatte il worker
            logger.exception("Errore del worker IA sulla sessione %s", session_id)
            with _lock:
                _counters["errors"] += 1
        finally:
            with _lock:
                _active.discard(session_id)
            _queue.task_done()


def start(workers: int = DEFAULT_WORKERS) -> None:
    """Avvia il pool (idempotente: i worker si creano una volta sola)."""
    with _lock:
        missing = max(0, int(workers)) - len(_threads)
        for _n in range(missing):
            t = threading.Thread(target=_worker_loop, daemon=True, name="ai-worker")
            _threads.append(t)
            t.start()


def started() -> bool:
    with _lock:
        return bool(_threads)


def enqueue(session_id: int) -> bool:
    """Accoda la sessione; False se è già in coda o in lavorazione (dedup)."""
    with _lock:
        if session_id in _pending or session_id in _active:
            return False
        _pending.add(session_id)
    _queue.put(session_id)
    return True


def is_scheduled(session_id: int) -> bool:
    """La sessione è in coda o in lavorazione? (il client mostra «l'IA pensa»)."""
    with _lock:
        return session_id in _pending or session_id in _active


def snapshot() -> dict:
    """Stato leggibile della coda (introspezione admin)."""
    with _lock:
        return {
            "workers": len(_threads),
            "queued": sorted(_pending),
            "active": sorted(_active),
            "done": _counters["done"],
            "errors": _counters["errors"],
        }


def recovery_scan(db) -> int:
    """Ri-accoda le partite rimaste al turno dell'IA (riavvio del server).

    Il DB è la fonte di verità: nessun job va perso perché nessun job vive
    fuori dal DB. Prima della coda le partite IA-vs-IA restavano ferme finché
    un client non le guardava; ora ripartono da sole all'avvio.
    """
    from . import gameplay  # import locale (ciclo)

    n = 0
    rows = db.query(models.GameSession).filter_by(status="in_progress").all()
    for session in rows:
        game = get_game(session.game.code)
        state = gameplay.load_state(game, session)
        if game.is_terminal(state):
            continue
        if gameplay.side_is_ai(session, game.current_player(state)) and enqueue(session.id):
            n += 1
    return n


def reset_for_tests() -> None:
    """Svuota lo stato della coda (SOLO test: l'ordine dei test è casuale)."""
    with _lock:
        _pending.clear()
        _active.clear()
        _counters["done"] = 0
        _counters["errors"] = 0
    while True:
        try:
            _queue.get_nowait()
            _queue.task_done()
        except queue.Empty:
            break
