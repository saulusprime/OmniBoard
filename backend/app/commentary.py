"""Commento della partita (solo scacchi): badge di qualità + commentatore LLM.

Dopo OGNI mossa (umana o IA) un lavoro in background:

1. valuta con Stockfish la posizione prima/dopo e CLASSIFICA la mossa — il
   badge (🌟 da maestro, 👍 buona, ⚔️ aggressiva, 🐔 codarda, 🤔 imprecisa,
   😬 errore, 🤡 blunder) finisce nel log della mossa (``moves_json``) e il
   client lo disegna in alto a destra del pezzo mosso;
2. se un provider IA è attivo (e ``commentary.llm`` è acceso), chiede al
   modello UNA battuta di commento in italiano, salvata accanto alla mossa e
   mostrata nel widget «🎙️ Commento» della pagina di gioco.

Tutto è best-effort: senza Stockfish niente badge, senza provider niente
commento, e nessun errore raggiunge mai la partita. Con ``AI_ASYNC=0`` (test)
il lavoro è sincrono. La valutazione della posizione precedente è memoizzata
per sessione: una sola ricerca nuova per mossa.
"""

from __future__ import annotations

import json
import os
import threading

from engine import get_game

from . import ai_providers, models, settings_service
from .database import SessionLocal
from .gameplay import history_ids
from .opponents import api_ai, stockfish

# Valutazione della posizione precedente, memoizzata per sessione:
# {session_id: (n_semimosse, cp_lato_bianco, mossa_migliore_suggerita)}.
_last_eval: dict[int, tuple[int, int, str | None]] = {}
_running: set[tuple[int, int]] = set()
_lock = threading.Lock()


def _classify(
    loss: int, *, is_best: bool, capture: bool, retreat: bool, sacrifice: bool = False
) -> tuple[str, str]:
    """(simbolo, etichetta) della mossa dal punto di vista di chi l'ha giocata."""
    if loss >= 200:
        return "🤡", "blunder"
    if loss >= 100:
        return "😬", "errore"
    if retreat and loss >= 50:
        return "🐔", "codarda"  # ripiega E perde terreno: la ritirata timida
    if loss >= 50:
        return "🤔", "imprecisa"
    if sacrifice and loss <= 30:
        # Mossa forte CHE offre materiale: la genialità vera (🌟 non distingue
        # i sacrifici). Il materiale offerto è misurato staticamente (SEE).
        return "💎", "geniale (sacrificio)"
    if is_best and loss <= 5:
        return "🌟", "da maestro"
    if capture and loss < 30:
        return "⚔️", "aggressiva"
    return "👍", "buona"


def schedule(session_id: int) -> None:
    """Commenta l'ULTIMA mossa della sessione (in background; sincrono nei test)."""
    if os.getenv("AI_ASYNC", "1") == "0":
        _run(session_id)
    else:
        threading.Thread(target=_run, args=(session_id,), daemon=True).start()


def _run(session_id: int) -> None:
    db = SessionLocal()
    try:
        session = db.get(models.GameSession, session_id)
        if session is None or session.game.code != "chess":
            return
        if not settings_service.get(db, "commentary.enabled"):
            return
        moves = json.loads(session.moves_json or "[]")
        if not moves or "quality" in moves[-1]:
            return
        ply = len(moves)
        with _lock:  # una sola classificazione per (sessione, semimossa)
            if (session_id, ply) in _running:
                return
            _running.add((session_id, ply))
        try:
            _tag_and_comment(db, session, moves, ply)
        finally:
            with _lock:
                _running.discard((session_id, ply))
    except Exception:  # noqa: BLE001 - il commento non deve mai rompere la partita
        pass
    finally:
        db.close()


def _is_sacrifice(game, session, history: list[str]) -> bool:
    """L'ultima mossa OFFRE materiale? (SEE dell'avversario sulla casa d'arrivo).

    Si rigioca la partita col motore puro (economico) fino alla mossa appena
    giocata; poi la Static Exchange Evaluation dice quanto l'avversario può
    vincere catturando il pezzo appena mosso, ricatture comprese: ≥ 2 pedoni
    netti = materiale davvero in offerta. Prudente: ogni dubbio → False.
    """
    try:
        from engine.chess.engine import _least_attacker, _see

        state = game.from_fen(session.start_fen) if session.start_fen else game.initial_state()
        for uci in history[:-1]:
            mv = next((m for m in game.legal_moves(state) if game.move_id(m) == uci), None)
            if mv is None:
                return False
            state = game.apply(state, mv)
        last = next((m for m in game.legal_moves(state) if game.move_id(m) == history[-1]), None)
        if last is None:
            return False
        after = game.apply(state, last)
        dest = last[1]
        occ = {sq: piece for sq, piece in enumerate(after.board) if piece is not None}
        attacker = _least_attacker(occ, dest, after.current)  # tocca all'avversario
        if attacker is None:
            return False  # il pezzo mosso non è nemmeno attaccato
        return _see(after.board, (attacker[0], dest, None)) >= 200
    except Exception:  # noqa: BLE001 - il badge non deve mai rompere la partita
        return False


def _tag_and_comment(db, session, moves: list, ply: int) -> None:
    cfg = stockfish.get_config(db)
    if not stockfish.is_available(cfg):
        return
    cfg = dict(cfg, elo=0, skill_level=20)
    cfg["move_ms"] = int(settings_service.get(db, "stockfish.analysis_ms"))
    history = history_ids(moves)
    # Partite da FEN: la parità segue il tratto iniziale e le posizioni UCI
    # ripartono dalla FEN (mai da startpos).
    start_fen = session.start_fen
    start_white = not (start_fen and start_fen.split()[1] == "b")
    mover_white = ((ply - 1) % 2 == 0) == start_white

    # Valutazione PRIMA della mossa: memoizzata dalla mossa precedente, oppure
    # ricalcolata (prima mossa della partita ≈ pari, nessuna ricerca in più).
    cached = _last_eval.get(session.id)
    if cached and cached[0] == ply - 1:
        cp_before, best_before = cached[1], cached[2]
    elif ply == 1 and not start_fen:
        cp_before, best_before = 0, None
    else:
        prefix = stockfish.uci_position(history[:-1], start_fen)
        ev = stockfish._ENGINE.evaluate(cfg, prefix)
        if ev is None:
            return
        cp_before = _white_cp(ev, white_to_move=mover_white)
        best_before = ev.get("best")

    ev_after = stockfish._ENGINE.evaluate(cfg, stockfish.uci_position(history, start_fen))
    if ev_after is None:
        return
    cp_after = _white_cp(ev_after, white_to_move=not mover_white)
    _last_eval[session.id] = (ply, cp_after, ev_after.get("best"))

    loss = (cp_before - cp_after) if mover_white else (cp_after - cp_before)
    uci = moves[-1].get("id", "")
    notation = moves[-1].get("notation", "")
    # Ritirata = il pezzo torna verso la propria prima traversa (dal punto di
    # vista di chi muove); cattura/scacco letti dalla notazione del motore.
    retreat = len(uci) >= 4 and (
        (int(uci[3]) < int(uci[1])) if mover_white else (int(uci[3]) > int(uci[1]))
    )
    is_best = bool(best_before) and uci == best_before
    # Il controllo del sacrificio (replay + SEE) si paga solo quando può fare
    # la differenza: mossa quasi-ottimale, mai sui pasticci.
    sacrifice = loss <= 30 and _is_sacrifice(get_game("chess"), session, history)
    symbol, label = _classify(
        max(0, int(loss)),
        is_best=is_best,
        capture="x" in notation or "+" in notation,
        retreat=retreat,
        sacrifice=sacrifice,
    )
    moves[-1]["quality"] = {"symbol": symbol, "label": label, "loss": max(0, int(loss))}

    # Commentatore LLM: una battuta in italiano dal provider attivo (best effort).
    if settings_service.get(db, "commentary.llm"):
        provider = ai_providers.get_active_config(db)
        if provider:
            game = get_game("chess")
            opening = game.opening_name(history) or "apertura fuori dai libri"
            prompt = (
                "Sei un arguto commentatore di scacchi in diretta, in italiano. "
                f"Semimossa {ply}: {'Bianco' if mover_white else 'Nero'} ha giocato "
                f"{notation} — giudizio del motore: {label} "
                f"(perdita {max(0, int(loss))} centipedoni; apertura: {opening}). "
                "Commenta in UNA frase breve, vivace e senza tecnicismi pesanti."
            )
            try:
                text = api_ai.guarded_complete(provider, prompt)
                if text:
                    moves[-1]["comment"] = " ".join(text.split())[:280]
            except Exception:  # noqa: BLE001 - niente commento, nessun danno
                pass

    session.moves_json = json.dumps(moves)
    db.commit()


def _white_cp(ev: dict, white_to_move: bool) -> int:
    if ev.get("mate") is not None:
        mate = ev["mate"]
        score = 10000 - min(abs(mate), 99) if mate > 0 else -10000 + min(abs(mate), 99)
    else:
        score = int(ev.get("cp") or 0)
    return score if white_to_move else -score
