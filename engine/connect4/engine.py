"""Motore dedicato di Forza 4: bitboard, negamax e approfondimento iterativo.

Molto più forte del minimax generico a profondità fissa 4:

- **bitboard** alla Fhourstones: 7 bit per colonna (bit 0 = riga in basso, il
  settimo è sentinella sempre vuoto); ``position`` = pedine di chi muove,
  ``mask`` = tutte le pedine. Vittorie e minacce si calcolano con shift e AND,
  ordini di grandezza più veloci delle quaterne su tuple;
- **tattica esatta a ogni nodo**: vittoria immediata, blocco forzato quando
  l'avversario minaccia, sconfitta dichiarata con doppia minaccia avversaria e
  divieto di giocare sotto una casella vincente avversaria — gli errori
  tattici del vecchio orizzonte a 4 semimosse spariscono;
- **transposition table** con flag alpha/beta esatti e mossa migliore in testa
  all'ordinamento (chiave ``position + mask``, unica per costruzione);
- **approfondimento iterativo** con budget di tempo (si tiene l'ultima
  profondità completata), ``jitter`` alla radice e ``stop`` esterno, come per
  scacchi e dama.

La valutazione alle foglie conta le **caselle vincenti** (vuote che
completerebbero una quaterna) di ciascun lato più il controllo della colonna
centrale, dal punto di vista di chi muove (negamax). Le vittorie valgono
``_WIN - semimosse``: a parità si preferisce la via più corta.
"""

from __future__ import annotations

import random
import time

ROWS = 6
COLS = 7
_H = ROWS + 1  # altezza della colonna nel bitboard (con la sentinella)

_BOTTOM = sum(1 << (c * _H) for c in range(COLS))  # riga in basso di ogni colonna
_BOARD = _BOTTOM * ((1 << ROWS) - 1)  # tutte le 42 celle reali
_COLUMN = [((1 << ROWS) - 1) << (c * _H) for c in range(COLS)]
_TOP = [1 << (c * _H + ROWS - 1) for c in range(COLS)]  # cella più alta di ogni colonna
_CENTER = _COLUMN[COLS // 2]

_ORDER = (3, 2, 4, 1, 5, 0, 6)  # colonne dal centro in fuori (ordinamento statico)
_WIN = 100_000
_WIN_NEAR = _WIN - 1000  # oltre: è un punteggio di vittoria, dipende dalla semimossa
_INF = 10**9
_SPOT = 16  # valore di una casella vincente nella valutazione
_CENTER_W = 3  # valore di una pedina nella colonna centrale

_EXACT, _LOWER, _UPPER = 0, 1, 2


class _TimeUp(Exception):
    pass


def from_state(state) -> tuple[int, int]:
    """Converte lo stato del gioco (tupla, riga 0 in alto) in ``(position, mask)``."""
    position = mask = 0
    for r in range(ROWS):
        for c in range(COLS):
            v = state.board[r * COLS + c]
            if v is None:
                continue
            bit = 1 << (c * _H + (ROWS - 1 - r))
            mask |= bit
            if v == state.current:
                position |= bit
    return position, mask


def _has_won(p: int) -> bool:
    m = p & (p >> 1)  # verticale
    if m & (m >> 2):
        return True
    for d in (_H, ROWS, ROWS + 2):  # orizzontale, diagonale /, diagonale \
        m = p & (p >> d)
        if m & (m >> (2 * d)):
            return True
    return False


def _winning_spots(p: int, mask: int) -> int:
    """Celle vuote che completerebbero una quaterna per ``p``."""
    r = (p << 1) & (p << 2) & (p << 3)  # verticale (si vince solo appoggiando sopra)
    for d in (_H, ROWS, ROWS + 2):
        t = (p << d) & (p << (2 * d))
        r |= t & (p << (3 * d))  # ppp_
        r |= t & (p >> d)  # p_pp… e combinazioni simmetriche
        t = (p >> d) & (p >> (2 * d))
        r |= t & (p << d)
        r |= t & (p >> (3 * d))
    return r & (_BOARD ^ mask)


def _eval(position: int, mask: int) -> int:
    """Valutazione statica dal punto di vista di chi muove."""
    opp = position ^ mask
    score = _SPOT * (
        (_winning_spots(position, mask)).bit_count() - (_winning_spots(opp, mask)).bit_count()
    )
    score += _CENTER_W * ((position & _CENTER).bit_count() - (opp & _CENTER).bit_count())
    return score


class _Ctx:
    def __init__(self, deadline, tt, stop):
        self.deadline = deadline
        self.tt = tt if tt is not None else {}
        self.stop = stop
        self.nodes = 0

    def tick(self):
        self.nodes += 1
        if (self.nodes & 511) == 0:
            if time.monotonic() > self.deadline:
                raise _TimeUp
            if self.stop is not None and self.stop.is_set():
                raise _TimeUp


def _negamax(ctx, position, mask, ply, depth, alpha, beta):
    ctx.tick()
    if mask == _BOARD:
        return 0  # tavoliere pieno: patta

    playable = (mask + _BOTTOM) & _BOARD  # cella d'atterraggio di ogni colonna non piena
    if _winning_spots(position, mask) & playable:
        return _WIN - (ply + 1)  # vittoria immediata di chi muove

    opp_spots = _winning_spots(position ^ mask, mask)
    opp_now = opp_spots & playable
    forced = 0
    if opp_now:
        if opp_now & (opp_now - 1):
            return -(_WIN - (ply + 2))  # doppia minaccia: qualunque cosa si giochi, si perde
        forced = opp_now  # una sola: il blocco è obbligato

    if depth <= 0:
        return _eval(position, mask)

    key = position + mask
    best_col = -1
    hit = ctx.tt.get(key)
    if hit is not None:
        h_depth, h_flag, h_value, best_col = hit
        if h_depth >= depth:
            if h_value >= _WIN_NEAR:
                h_value -= ply
            elif h_value <= -_WIN_NEAR:
                h_value += ply
            if (
                h_flag == _EXACT
                or (h_flag == _LOWER and h_value >= beta)
                or (h_flag == _UPPER and h_value <= alpha)
            ):
                return h_value

    # Mai giocare sotto una casella vincente avversaria (regalo immediato).
    safe = playable & ~(opp_spots >> 1)
    if forced:
        safe = forced
    if not safe:
        return -(_WIN - (ply + 2))  # solo mosse che consegnano la partita

    alpha0 = alpha
    best = -_INF
    cols = _ORDER if best_col < 0 else (best_col, *(c for c in _ORDER if c != best_col))
    for col in cols:
        move = safe & _COLUMN[col]
        if not move:
            continue
        score = -_negamax(ctx, position ^ mask, mask | move, ply + 1, depth - 1, -beta, -alpha)
        if score > best:
            best = score
            best_col = col
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break

    flag = _EXACT if alpha0 < best < beta else (_LOWER if best >= beta else _UPPER)
    value = best
    if value >= _WIN_NEAR:
        value += ply
    elif value <= -_WIN_NEAR:
        value -= ply
    ctx.tt[key] = (depth, flag, value, best_col)
    return best


def best_move(game, state, time_limit=2.0, max_depth=None, jitter=0, tt=None, stop=None):
    """La colonna migliore entro il budget; None solo senza mosse legali."""
    moves = list(game.legal_moves(state))
    if not moves:
        return None
    if len(moves) == 1:
        return moves[0]

    position, mask = from_state(state)
    playable = (mask + _BOTTOM) & _BOARD
    wins = _winning_spots(position, mask) & playable
    if wins:  # vittoria in una: inutile pensare
        for col in _ORDER:
            if wins & _COLUMN[col] and col in moves:
                return col
    if max_depth is None:
        max_depth = ROWS * COLS - mask.bit_count()  # al più fino a tavoliere pieno

    ctx = _Ctx(time.monotonic() + max(0.05, float(time_limit)), tt, stop)
    # La finestra delle mosse dopo la prima si restringe, ma con un MARGINE pari
    # al jitter: ogni mossa che può entrare nel pool finale ha un punteggio
    # esatto, mai un bound (un bound pari ad alpha creerebbe falsi pareggi con
    # la migliore, e il sorteggio potrebbe scegliere una mossa in realtà persa).
    margin = int(jitter) + 1
    best_scored: list[tuple[float, int]] = []
    try:
        for depth in range(2, max_depth + 1):
            scored = []
            alpha = -_INF
            for col in _ORDER:
                if col not in moves:
                    continue
                move = (mask + (_BOTTOM & _COLUMN[col])) & _COLUMN[col]
                beta = _INF if alpha == -_INF else -alpha + margin + 1
                score = -_negamax(ctx, position ^ mask, mask | move, 1, depth - 1, -_INF, beta)
                scored.append((score, col))
                if score > alpha:
                    alpha = score
            best_scored = scored  # profondità COMPLETATA: si può usare
            if alpha >= _WIN_NEAR:
                break  # vittoria forzata trovata: approfondire non cambia nulla
    except _TimeUp:
        pass
    if not best_scored:
        return moves[0]

    top = max(s for s, _c in best_scored)
    pool = [c for s, c in best_scored if s >= top - jitter]
    return random.choice(pool) if len(pool) > 1 else pool[0]
