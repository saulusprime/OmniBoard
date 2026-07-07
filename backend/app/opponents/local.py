"""Giocatore **locale**: il ripiego sempre disponibile, senza dipendenze esterne.

Non è un tipo di avversario selezionabile: entra in gioco quando l'avversario scelto
(Stockfish o IA via API) non può muovere — binario mancante, provider non configurato,
errore di rete, risposta non valida — così la partita non si blocca mai.

Due livelli:
- per i giochi con un **motore dedicato** (scacchi: ``engine_move``, alpha-beta con
  quiescence e transposition table) si usa quello, con budget di tempo;
- per gli altri giochi, un **minimax generico** con potatura alpha-beta: ricerca
  completa per i giochi piccoli (Tris, ``search_depth=None``) e a profondità limitata
  con ``Game.heuristic`` per quelli grandi (Forza 4, Dama).
"""

from __future__ import annotations

import os
import random

_WIN = 1_000_000.0
_POS_INF = float("inf")
_NEG_INF = float("-inf")


def engine_time(think_ms=None) -> float:
    """Budget di tempo (secondi) per il motore dedicato.

    ``think_ms`` viene di norma dal parametro ``ai.engine_ms`` (super admin); se assente
    si usa ``AI_ENGINE_MS`` (default 2000). ``AI_ENGINE_MS_MAX``, se impostata, è un tetto
    massimo applicato sempre (kill-switch operativo; nei test la limita per velocità).
    """
    t = float(os.getenv("AI_ENGINE_MS", "2000")) if think_ms is None else float(think_ms)
    cap = os.getenv("AI_ENGINE_MS_MAX")
    if cap:
        t = min(t, float(cap))
    return max(0.05, t / 1000.0)


# Livelli di difficoltà del MOTORE LOCALE, selezionabili al setup della partita
# (per i lati di tipo "ai"; la colonna è la stessa dei preset Stockfish).
# think_ms None = si usa il parametro globale ai.engine_ms; jitter alto = il
# motore sceglie tra mosse anche molto lontane dalla migliore (errori "umani").
# Pensati per gli scacchi (tempo e jitter agiscono sul motore dedicato); negli
# altri giochi il minimax generico ne è poco influenzato.
ENGINE_LEVELS: dict[str, dict] = {
    "maestro": {"label": "Maestro (piena forza)", "think_ms": None, "jitter": 0},
    "esperto": {"label": "Esperto (forte)", "think_ms": 1200, "jitter": 15},
    "medio": {"label": "Medio (circolo)", "think_ms": 500, "jitter": 60},
    "apprendista": {"label": "Apprendista (facile)", "think_ms": 200, "jitter": 150},
    "novizio": {"label": "Novizio (per imparare)", "think_ms": 100, "jitter": 300},
}


def level_label(level: str | None) -> str | None:
    """Etichetta leggibile del livello del motore locale; None se sconosciuto."""
    preset = ENGINE_LEVELS.get(level or "")
    return preset["label"] if preset else None


def best_move(game, state, legal, history=None, think_ms=None, jitter=0, style=None, tt=None):
    """Miglior mossa del giocatore locale. Ritorna ``(mossa, sorgente)``.

    ``sorgente`` ∈ {"engine" (motore dedicato), "local" (minimax generico)}.
    ``style`` (aggression/contempt) arriva dal profilo dell'avversario; ``jitter``
    varia la scelta tra mosse quasi-ottimali per non ripetere partite identiche.
    """
    engine_move = getattr(game, "engine_move", None)
    if callable(engine_move):
        move = engine_move(
            state,
            history=history,
            time_limit=engine_time(think_ms),
            style=style,
            jitter=jitter,
            tt=tt,  # TT condivisa dal pondering (se attivo per la sessione)
        )
        if move is not None and move in legal:
            return move, "engine"
    return _minimax_move(game, state, legal), "local"


# ----- Minimax generico con potatura alpha-beta -----
def _minimax_move(game, state, legal):
    me = game.current_player(state)
    depth = getattr(game, "search_depth", None)  # None = ricerca completa (giochi piccoli)
    best_score = None
    best_moves: list = []
    for move in legal:
        next_depth = None if depth is None else depth - 1
        score = _search(game, game.apply(state, move), me, next_depth, _NEG_INF, _POS_INF)
        if best_score is None or score > best_score:
            best_score = score
            best_moves = [move]
        elif score == best_score:
            best_moves.append(move)
    # Scelta casuale tra le mosse ugualmente ottimali: le partite consecutive variano.
    return random.choice(best_moves)


def _search(game, state, me, depth, alpha, beta):
    if game.is_terminal(state):
        winner = game.outcome(state).winner
        return 0.0 if winner is None else (_WIN if winner == me else -_WIN)
    if depth == 0:
        return float(game.heuristic(state, me))
    next_depth = None if depth is None else depth - 1
    if game.current_player(state) == me:
        value = _NEG_INF
        for m in game.legal_moves(state):
            value = max(value, _search(game, game.apply(state, m), me, next_depth, alpha, beta))
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        return value
    value = _POS_INF
    for m in game.legal_moves(state):
        value = min(value, _search(game, game.apply(state, m), me, next_depth, alpha, beta))
        beta = min(beta, value)
        if beta <= alpha:
            break
    return value
