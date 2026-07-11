"""Motore dedicato del Gomoku: candidati vicini + alpha-beta iterativo.

Il minimax generico non può giocare a Gomoku (225 rami): questo motore
restringe la ricerca alle mosse sensate e tiene la tattica corta esatta.

- **candidati**: solo le intersezioni vuote entro distanza 2 (Chebyshev) da
  una pietra (prima mossa: il centro), ordinate per guadagno locale e
  potate ai migliori ``_K`` per nodo;
- **tattica esatta a ogni nodo**: cinquina immediata di chi muove; se
  l'avversario ha più intersezioni vincenti la sconfitta è dichiarata, con
  una sola il blocco è forzato;
- **valutazione incrementale**: punteggio per finestre di 5 (pesi crescenti
  per 1-4 pietre in finestra non contesa) aggiornato per DELTA alla posa —
  la foglia costa O(1);
- **approfondimento iterativo** con budget di tempo e ``jitter`` alla radice
  (finestra con MARGINE pari al jitter: i punteggi del pool sono esatti,
  mai bound — la lezione del falso pareggio di Forza 4/dama).
"""

from __future__ import annotations

import random
import time

ROWS = 15
COLS = 15
_N = ROWS * COLS
_WIN = 1_000_000
_INF = 10**9
_K = 10  # rami per nodo dopo l'ordinamento
# Peso di una finestra con n pietre proprie e nessuna avversaria (indice n).
_P = (0, 1, 12, 128, 1280, 200_000)


def _build_windows() -> tuple:
    wins = []
    for r in range(ROWS):
        for c in range(COLS):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                rr, cc = r + 4 * dr, c + 4 * dc
                if 0 <= rr < ROWS and 0 <= cc < COLS:
                    wins.append(tuple((r + k * dr) * COLS + (c + k * dc) for k in range(5)))
    return tuple(wins)


_WINDOWS = _build_windows()
# Indici delle finestre passanti per ogni cella.
_at_build: list[list[int]] = [[] for _ in range(_N)]
for _wi, _w in enumerate(_WINDOWS):
    for _cell in _w:
        _at_build[_cell].append(_wi)
_AT: tuple[tuple[int, ...], ...] = tuple(tuple(ws) for ws in _at_build)

# Intorno Chebyshev ≤ 2 di ogni cella (per i candidati).
_NEAR: list[tuple[int, ...]] = []
for _i in range(_N):
    _r, _c = divmod(_i, COLS)
    _NEAR.append(
        tuple(
            (_r + dr) * COLS + (_c + dc)
            for dr in range(-2, 3)
            for dc in range(-2, 3)
            if (dr or dc) and 0 <= _r + dr < ROWS and 0 <= _c + dc < COLS
        )
    )


def _val(n0: int, n1: int) -> int:
    """Valore (per il Nero) di una finestra con n0 pietre nere e n1 bianche."""
    if n0 and n1:
        return 0  # finestra contesa: nessuno può più chiuderla
    if n0:
        return _P[n0]
    if n1:
        return -_P[n1]
    return 0


def static_score(board, player: int) -> int:
    """Punteggio statico dell'intera posizione dal punto di vista di ``player``."""
    score0 = 0
    for w in _WINDOWS:
        n0 = n1 = 0
        for i in w:
            v = board[i]
            if v == 0:
                n0 += 1
            elif v == 1:
                n1 += 1
        score0 += _val(n0, n1)
    return score0 if player == 0 else -score0


def _delta(board, cell: int, player: int) -> int:
    """Variazione del punteggio (per il Nero) se ``player`` posa in ``cell``."""
    d = 0
    for wi in _AT[cell]:
        n0 = n1 = 0
        for i in _WINDOWS[wi]:
            v = board[i]
            if v == 0:
                n0 += 1
            elif v == 1:
                n1 += 1
        before = _val(n0, n1)
        after = _val(n0 + 1, n1) if player == 0 else _val(n0, n1 + 1)
        d += after - before
    return d


def _wins_at(board, cell: int, player: int) -> bool:
    """True se posare in ``cell`` completa una fila di 5+ per ``player``."""
    r0, c0 = divmod(cell, COLS)
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        n = 1
        for sign in (1, -1):
            r, c = r0 + dr * sign, c0 + dc * sign
            while 0 <= r < ROWS and 0 <= c < COLS and board[r * COLS + c] == player:
                n += 1
                r += dr * sign
                c += dc * sign
        if n >= 5:
            return True
    return False


def _candidates(board) -> list[int]:
    out: set[int] = set()
    for i in range(_N):
        if board[i] is not None:
            for j in _NEAR[i]:
                if board[j] is None:
                    out.add(j)
    return list(out)


def _ordered(board, cands, side: int, limit: int) -> list[int]:
    """I candidati migliori per ``side``: guadagno proprio + valore difensivo."""
    scored = []
    for c in cands:
        own = _delta(board, c, side)
        opp = _delta(board, c, 1 - side)
        gain = (own - opp) if side == 0 else (opp - own)  # entrambi in POV Nero
        scored.append((gain, c))
    scored.sort(reverse=True)
    return [c for _g, c in scored[:limit]]


class _TimeUp(Exception):
    pass


class _Ctx:
    def __init__(self, deadline, stop):
        self.deadline = deadline
        self.stop = stop
        self.nodes = 0

    def tick(self):
        self.nodes += 1
        if (self.nodes & 63) == 0:
            if time.monotonic() > self.deadline:
                raise _TimeUp
            if self.stop is not None and self.stop.is_set():
                raise _TimeUp


def _negamax(ctx, board, side, ply, depth, alpha, beta, score0):
    ctx.tick()
    cands = _candidates(board)
    if not cands:
        return 0  # goban pieno: patta
    for c in cands:
        if _wins_at(board, c, side):
            return _WIN - (ply + 1)  # cinquina immediata di chi muove
    blocks = [c for c in cands if _wins_at(board, c, 1 - side)]
    if len(blocks) > 1:
        return -(_WIN - (ply + 2))  # doppia minaccia di cinquina: persa
    if depth <= 0:
        return score0 if side == 0 else -score0
    pool = blocks if blocks else _ordered(board, cands, side, _K)
    best = -_INF
    for c in pool:
        d = _delta(board, c, side)
        board[c] = side
        score = -_negamax(ctx, board, 1 - side, ply + 1, depth - 1, -beta, -alpha, score0 + d)
        board[c] = None
        if score > best:
            best = score
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break
    return best


def best_move(game, state, time_limit=2.0, max_depth=6, jitter=0, stop=None):
    """La mossa migliore entro il budget; None solo senza mosse legali."""
    moves = game.legal_moves(state)
    if not moves:
        return None
    board = list(state.board)
    me = state.current
    if all(v is None for v in board):
        return (ROWS // 2) * COLS + COLS // 2  # prima pietra: il centro

    cands = _candidates(board)
    for c in cands:
        if _wins_at(board, c, me):
            return c  # cinquina in una: inutile pensare
    blocks = [c for c in cands if _wins_at(board, c, 1 - me)]
    root = blocks if blocks else _ordered(board, cands, me, _K)
    if len(root) == 1:
        return root[0]

    ctx = _Ctx(time.monotonic() + max(0.05, float(time_limit)), stop)
    score0 = static_score(board, 0)
    margin = int(jitter) + 1
    best_scored: list[tuple[float, int]] = []
    try:
        for depth in range(1, max_depth + 1):
            scored = []
            alpha = -_INF
            for c in root:
                d = _delta(board, c, me)
                board[c] = me
                beta = _INF if alpha == -_INF else -alpha + margin + 1
                score = -_negamax(ctx, board, 1 - me, 1, depth - 1, -_INF, beta, score0 + d)
                board[c] = None
                scored.append((score, c))
                if score > alpha:
                    alpha = score
            best_scored = scored  # profondità COMPLETATA: si può usare
            if alpha >= _WIN - 100:
                break  # vittoria forzata trovata
    except _TimeUp:
        # Il tempo può scadere fra posa e ritiro: ``board`` resta sporca, ma da
        # qui in poi non si usa più (i punteggi validi sono in best_scored).
        pass
    if not best_scored:
        return root[0]

    top = max(s for s, _c in best_scored)
    pool = [c for s, c in best_scored if s >= top - jitter]
    return random.choice(pool) if len(pool) > 1 else pool[0]
