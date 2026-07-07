"""Analisi post-partita con Stockfish: valutazione mossa per mossa, errori marcati.

Per una partita di SCACCHI conclusa si valuta ogni posizione della storia (movetime
``stockfish.analysis_ms`` a posizione) e per ogni mossa si calcola quanto ha perso
chi l'ha giocata rispetto alla valutazione precedente. Le mosse vengono marcate:
``??`` (blunder, ≥ 2 pedoni persi), ``?`` (errore, ≥ 1), ``?!`` (imprecisione, ≥ 0,5).

Le valutazioni sono in centipedoni dal punto di vista del BIANCO (i matti diventano
±(10000 − distanza), così il grafico resta ordinabile). Il risultato è salvato in
``game_sessions.analysis_json``: si calcola una volta sola per partita.

Il lavoro gira in un thread (come le mosse IA): 60-100 posizioni × ~200 ms ≈ 15-25 s.
Con ``AI_ASYNC=0`` (i test) l'analisi è sincrona e deterministica.
"""

from __future__ import annotations

import json
import os
import threading

from . import models, settings_service
from .database import SessionLocal
from .gameplay import history_ids
from .opponents import stockfish

# Sessioni con un'analisi in corso (evita doppi avvii dallo stesso pulsante).
_running: set[int] = set()
_lock = threading.Lock()

# Soglie di perdita (centipedoni) per le etichette degli errori.
_TAGS = [(200, "??"), (100, "?"), (50, "?!")]


def _white_cp(ev: dict, white_to_move: bool) -> int:
    """Score UCI (relativo a chi muove) → centipedoni dal punto di vista del bianco."""
    if ev.get("mate") is not None:
        mate = ev["mate"]
        # Matto in N: quasi-infinito, meno la distanza (conserva l'ordinamento).
        score = 10000 - min(abs(mate), 99) if mate > 0 else -10000 + min(abs(mate), 99)
    else:
        score = int(ev.get("cp") or 0)
    return score if white_to_move else -score


def start(session_id: int) -> bool:
    """Avvia (o esegue subito, nei test) l'analisi; False se già in corso."""
    with _lock:
        if session_id in _running:
            return False
        _running.add(session_id)
    if os.getenv("AI_ASYNC", "1") == "0":
        _run(session_id)
    else:
        threading.Thread(target=_run, args=(session_id,), daemon=True).start()
    return True


def _run(session_id: int) -> None:
    db = SessionLocal()
    try:
        session = db.get(models.GameSession, session_id)
        if session is None:
            return
        cfg = stockfish.get_config(db)
        cfg["move_ms"] = int(settings_service.get(db, "stockfish.analysis_ms"))
        # La forza si analizza a piena potenza: niente limiti Elo/skill.
        cfg.update(elo=0, skill_level=20)
        moves = json.loads(session.moves_json or "[]")
        uci_history = history_ids(moves)

        # Partite da FEN: le posizioni ripartono dalla FEN e la parità delle
        # semimosse segue il tratto iniziale (il Nero può muovere per primo).
        start_fen = session.start_fen
        start_white = not (start_fen and start_fen.split()[1] == "b")

        evals: list[dict] = []
        prev_cp = 0  # posizione iniziale standard ≈ pari (evitiamo una ricerca in più)
        best_before: str | None = None
        ok = True
        if start_fen:
            ev0 = stockfish._ENGINE.evaluate(cfg, stockfish.uci_position([], start_fen))
            if ev0 is not None:
                prev_cp = _white_cp(ev0, white_to_move=start_white)
                best_before = ev0.get("best")
        for i, uci in enumerate(uci_history):
            position = stockfish.uci_position(uci_history[: i + 1], start_fen)
            ev = stockfish._ENGINE.evaluate(cfg, position)
            if ev is None:  # binario mancante o morto: analisi non disponibile
                ok = False
                break
            white_to_move = ((i + 1) % 2 == 0) == start_white  # chi muove dopo i+1 semimosse
            cp = _white_cp(ev, white_to_move)
            mover_white = (i % 2 == 0) == start_white
            loss = (prev_cp - cp) if mover_white else (cp - prev_cp)
            tag = next((t for limit, t in _TAGS if loss >= limit), None)
            evals.append(
                {
                    "ply": i + 1,
                    "by": "x" if mover_white else "o",
                    "cp": cp,  # dopo la mossa, punto di vista del bianco
                    "loss": max(0, int(loss)),
                    "tag": tag,
                    # Il suggerimento del motore per QUESTA mossa è il bestmove
                    # calcolato sulla posizione precedente.
                    "best": best_before,
                }
            )
            prev_cp = cp
            best_before = ev.get("best")

        session.analysis_json = json.dumps(
            {
                "status": "done" if ok else "failed",
                "detail": None if ok else "Stockfish non disponibile per l'analisi",
                "analysis_ms": cfg["move_ms"],
                "evals": evals if ok else [],
            }
        )
        db.commit()
        # L'analisi alimenta accuracy e debolezze del profilo: voci da rifare.
        from . import profile_cache

        for uid in (session.x_user_id, session.o_user_id):
            if uid:
                profile_cache.invalidate(uid)
    finally:
        db.close()
        with _lock:
            _running.discard(session_id)


def analyze_history(db, user_id: int, limit: int = 5) -> int:
    """Accoda l'analisi delle ultime partite di scacchi dell'utente NON ancora analizzate.

    Arricchisce la stima delle blunder del profilo (che legge solo la cache).
    I job condividono il processo Stockfish persistente (si serializzano sul suo
    lock). Ritorna quante partite sono state accodate.
    """
    from sqlalchemy import or_  # import locale: evita dipendenze in cima al modulo

    sessions = (
        db.query(models.GameSession)
        .join(models.Game)
        .filter(
            models.Game.code == "chess",
            models.GameSession.status == "finished",
            models.GameSession.analysis_json.is_(None),
            or_(
                models.GameSession.x_user_id == user_id,
                models.GameSession.o_user_id == user_id,
            ),
        )
        .order_by(models.GameSession.id.desc())
        .limit(max(1, min(int(limit), 10)))
        .all()
    )
    return sum(1 for s in sessions if start(s.id))


def is_running(session_id: int) -> bool:
    with _lock:
        return session_id in _running
