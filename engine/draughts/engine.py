"""Motore dedicato della dama: alpha-beta con approfondimento iterativo.

Molto più forte del minimax generico a profondità fissa 4:

- **approfondimento iterativo** con budget di tempo (si tiene la migliore
  dell'ultima profondità completata);
- **estensione delle catture**: a profondità esaurita, finché ci sono prese
  obbligatorie la ricerca continua (le catture in dama sono forzate: fermarsi a
  metà di uno scambio produce valutazioni assurde — l'orizzonte classico);
- **transposition table** per (scacchiera, tratto) con profondità preferita;
- ``jitter`` alla radice (scelta tra mosse quasi-ottimali, partite variate) e
  ``stop`` esterno (compatibilità con la catena ``engine_move`` della
  piattaforma; ``tt`` iniettabile come per gli scacchi).

La valutazione alle foglie è ``game.heuristic`` (materiale + trincea + centro),
dal punto di vista di chi deve muovere (negamax).
"""

from __future__ import annotations

import random
import time

_INF = 10**9
_EXT_LIMIT = -8  # tetto dell'estensione catture (semimosse oltre la profondità)


class _TimeUp(Exception):
    pass


class _Ctx:
    def __init__(self, game, deadline, tt, stop):
        self.game = game
        self.deadline = deadline
        self.tt = tt if tt is not None else {}
        self.stop = stop
        self.nodes = 0

    def tick(self):
        self.nodes += 1
        if (self.nodes & 255) == 0:
            if time.monotonic() > self.deadline:
                raise _TimeUp
            if self.stop is not None and self.stop.is_set():
                raise _TimeUp


def _negamax(ctx, state, depth, alpha, beta):
    ctx.tick()
    game = ctx.game
    moves = game.legal_moves(state)
    if not moves:
        return -_INF + 1  # chi non muove ha perso (regola della dama)
    # Le catture sono esclusive: se una mossa legale salta di due traverse, TUTTE
    # sono prese obbligatorie (niente secondo giro di generazione).
    forced = abs(moves[0][1] // 8 - moves[0][0] // 8) == 2
    if depth <= 0 and (not forced or depth <= _EXT_LIMIT):
        return game.heuristic(state, state.current)

    # TT senza flag alpha/beta (semplificazione accettata: piccole imprecisioni
    # di bound in cambio di molta velocità; il gioco resta tatticamente sano).
    key = (state.board, state.current)
    hit = ctx.tt.get(key)
    if hit is not None and hit[0] >= depth:
        return hit[1]

    best = -_INF
    for move in moves:
        score = -_negamax(ctx, game.apply(state, move), depth - 1, -beta, -alpha)
        if score > best:
            best = score
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break
    ctx.tt[key] = (depth, best)
    return best


def best_move(game, state, time_limit=2.0, max_depth=24, jitter=0, tt=None, stop=None):
    """La mossa migliore entro il budget; None solo senza mosse legali."""
    moves = game.legal_moves(state)
    if not moves:
        return None
    if len(moves) == 1:
        return moves[0]  # presa obbligata o mossa unica: inutile pensare

    ctx = _Ctx(game, time.monotonic() + max(0.05, float(time_limit)), tt, stop)
    # Finestra ristretta con MARGINE pari al jitter: ogni mossa che può entrare
    # nel pool finale deve avere un punteggio esatto, mai un bound (un bound
    # pari ad alpha creerebbe un falso pareggio con la migliore e il sorteggio
    # potrebbe scegliere una mossa in realtà perdente).
    margin = int(jitter) + 1
    best_scored: list[tuple[float, tuple]] = []
    try:
        for depth in range(2, max_depth + 1):
            scored = []
            alpha = -_INF
            for move in moves:
                beta = _INF if alpha == -_INF else -alpha + margin + 1
                score = -_negamax(ctx, game.apply(state, move), depth - 1, -_INF, beta)
                scored.append((score, move))
                if score > alpha:
                    alpha = score
            best_scored = scored  # profondità COMPLETATA: si può usare
    except _TimeUp:
        pass
    if not best_scored:
        return moves[0]

    top = max(s for s, _m in best_scored)
    pool = [m for s, m in best_scored if s >= top - jitter]
    return random.choice(pool) if len(pool) > 1 else pool[0]
