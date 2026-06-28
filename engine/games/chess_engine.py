"""Motore di ricerca per gli scacchi: molto più forte del minimax generico.

Tecniche implementate (tutte in puro Python, sopra il modello di ``chess.py``):

- **Iterative deepening** con limite di tempo: il motore approfondisce la ricerca finché
  c'è tempo e restituisce sempre la miglior mossa dell'ultima profondità completata.
- **Alpha-beta** in forma negamax con **transposition table** (riconosce posizioni già
  analizzate, anche per trasposizione di mosse).
- **Quiescence search**: dalle foglie estende solo catture/promozioni (e tutte le mosse
  se sotto scacco) per evitare l'*horizon effect* (valutare una posizione a metà di uno
  scambio). È ciò che impedisce all'IA di "regalare" pezzi.
- **Ordinamento delle mosse**: mossa della TT, catture per MVV-LVA, promozioni, *killer
  moves* e *history heuristic* → molti più tagli alpha-beta, quindi più profondità.
- **Valutazione**: materiale + tabelle posizionali (piece-square) per fase di gioco,
  struttura pedonale (pedoni doppiati/isolati/passati), coppia degli alfieri, torri su
  colonna aperta, sicurezza del re (scudo pedonale), tempo.

Il parametro ``style`` (opzionale) consente di modulare il gioco — ad es. *contempt*
(avversione alla patta) e *aggression* (peso dell'attacco al re) — ed è il punto in cui si
innesta il modello dell'avversario (schemi e debolezze).
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from .chess import WHITE

# Valori dei pezzi (centipedoni).
_VAL = {"P": 100, "N": 320, "B": 330, "R": 500, "Q": 900, "K": 20000}

MATE = 30000
_INF = 10**9
_TEMPO = 10

# Tabelle posizionali (Simplified Evaluation Function), dal punto di vista del Bianco e
# nello stesso indice della board: indice 0 = a8 (riga 0 = traversa 8). Per il Nero si
# specchia verticalmente (mirror) e si sottrae.
# fmt: off
_PST_P = [
     0,  0,  0,  0,  0,  0,  0,  0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
     5,  5, 10, 25, 25, 10,  5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5, -5,-10,  0,  0,-10, -5,  5,
     5, 10, 10,-20,-20, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0,
]
_PST_N = [
    -50,-40,-30,-30,-30,-30,-40,-50,
    -40,-20,  0,  0,  0,  0,-20,-40,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,
    -30,  0, 15, 20, 20, 15,  0,-30,
    -30,  5, 10, 15, 15, 10,  5,-30,
    -40,-20,  0,  5,  5,  0,-20,-40,
    -50,-40,-30,-30,-30,-30,-40,-50,
]
_PST_B = [
    -20,-10,-10,-10,-10,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5, 10, 10,  5,  0,-10,
    -10,  5,  5, 10, 10,  5,  5,-10,
    -10,  0, 10, 10, 10, 10,  0,-10,
    -10, 10, 10, 10, 10, 10, 10,-10,
    -10,  5,  0,  0,  0,  0,  5,-10,
    -20,-10,-10,-10,-10,-10,-10,-20,
]
_PST_R = [
     0,  0,  0,  0,  0,  0,  0,  0,
     5, 10, 10, 10, 10, 10, 10,  5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
     0,  0,  0,  5,  5,  0,  0,  0,
]
_PST_Q = [
    -20,-10,-10, -5, -5,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5,  5,  5,  5,  0,-10,
     -5,  0,  5,  5,  5,  5,  0, -5,
      0,  0,  5,  5,  5,  5,  0, -5,
    -10,  5,  5,  5,  5,  5,  0,-10,
    -10,  0,  5,  0,  0,  0,  0,-10,
    -20,-10,-10, -5, -5,-10,-10,-20,
]
_PST_K_MID = [
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -20,-30,-30,-40,-40,-30,-30,-20,
    -10,-20,-20,-20,-20,-20,-20,-10,
     20, 20,  0,  0,  0,  0, 20, 20,
     20, 30, 10,  0,  0, 10, 30, 20,
]
_PST_K_END = [
    -50,-40,-30,-20,-20,-30,-40,-50,
    -30,-20,-10,  0,  0,-10,-20,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-30,  0,  0,  0,  0,-30,-30,
    -50,-30,-30,-30,-30,-30,-30,-50,
]
# fmt: on
_PST = {"P": _PST_P, "N": _PST_N, "B": _PST_B, "R": _PST_R, "Q": _PST_Q}
_MIRROR = [(7 - (sq // 8)) * 8 + (sq % 8) for sq in range(64)]


class TimeUp(Exception):
    """Sollevata internamente quando scade il budget di tempo della ricerca."""


@dataclass
class _Ctx:
    game: object
    deadline: float
    tt: dict = field(default_factory=dict)
    killers: dict = field(default_factory=dict)
    history: dict = field(default_factory=dict)
    nodes: int = 0
    allow_timeout: bool = False
    contempt: int = 0
    aggression: float = 1.0
    jitter: int = 0
    root_side: int = 0

    def tick(self):
        self.nodes += 1
        if self.allow_timeout and (self.nodes & 2047) == 0 and time.monotonic() > self.deadline:
            raise TimeUp


def style_from_profile(profile):
    """Converte un profilo avversario in parametri di stile (riempito allo step 2)."""
    if not profile:
        return None
    return {
        "contempt": int(profile.get("contempt", 0)),
        "aggression": float(profile.get("aggression", 1.0)),
    }


# ----- Valutazione -----
def _is_endgame(npm_w, npm_b):
    # Finale: poco materiale pesante per entrambi (≈ assenza di donne / pochi pezzi).
    return npm_w <= 1300 and npm_b <= 1300


def evaluate(game, state, ctx=None):
    """Valutazione statica dal punto di vista del giocatore al tratto (centipedoni)."""
    board = state.board
    white = 0
    npm_w = npm_b = 0
    bishops_w = bishops_b = 0
    wp_files = [0] * 8
    bp_files = [0] * 8
    wp = []
    bp = []
    wk = bk = None
    for sq, p in enumerate(board):
        if p is None:
            continue
        kind = p.upper()
        is_white = p.isupper()
        if kind == "P":
            (wp if is_white else bp).append(sq)
            (wp_files if is_white else bp_files)[sq % 8] += 1
        elif kind == "K":
            if is_white:
                wk = sq
            else:
                bk = sq
        else:
            npm = _VAL[kind]
            if is_white:
                npm_w += npm
            else:
                npm_b += npm
            if kind == "B":
                if is_white:
                    bishops_w += 1
                else:
                    bishops_b += 1

    endgame = _is_endgame(npm_w, npm_b)
    for sq, p in enumerate(board):
        if p is None:
            continue
        kind = p.upper()
        is_white = p.isupper()
        val = _VAL[kind]
        if kind == "K":
            table = _PST_K_END if endgame else _PST_K_MID
            val += table[sq] if is_white else table[_MIRROR[sq]]
        else:
            table = _PST[kind]
            val += table[sq] if is_white else table[_MIRROR[sq]]
        white += val if is_white else -val

    # Coppia degli alfieri.
    if bishops_w >= 2:
        white += 30
    if bishops_b >= 2:
        white -= 30

    white += _pawn_structure(wp, wp_files, bp_files, WHITE)
    white -= _pawn_structure(bp, bp_files, wp_files, 1 - WHITE)
    white += _rooks_open_files(board, wp_files, bp_files)
    aggr = ctx.aggression if ctx else 1.0
    white += int(_king_safety(board, wk, wp_files, WHITE) * aggr)
    white -= int(_king_safety(board, bk, bp_files, 1 - WHITE) * aggr)

    rel = white if state.current == WHITE else -white
    return rel + _TEMPO


def _pawn_structure(pawns, own_files, enemy_files, color):
    score = 0
    for sq in pawns:
        f = sq % 8
        r = sq // 8
        # Doppiati: penalità per ogni pedone oltre il primo sulla colonna.
        if own_files[f] > 1:
            score -= 8
        # Isolati: nessun pedone amico sulle colonne adiacenti.
        if (f == 0 or own_files[f - 1] == 0) and (f == 7 or own_files[f + 1] == 0):
            score -= 15
        # Passati: nessun pedone nemico davanti sulla colonna o sulle adiacenti.
        ahead_clear = True
        for df in (-1, 0, 1):
            nf = f + df
            if 0 <= nf <= 7 and enemy_files[nf] > 0:
                ahead_clear = False
                break
        if ahead_clear:
            # Più avanzato = più prezioso (in traverse dal punto di vista del colore).
            adv = (6 - r) if color == WHITE else (r - 1)
            score += 10 + max(0, adv) * 8
    return score


def _rooks_open_files(board, wp_files, bp_files):
    score = 0
    for sq, p in enumerate(board):
        if p == "R":
            f = sq % 8
            if wp_files[f] == 0 and bp_files[f] == 0:
                score += 15
            elif wp_files[f] == 0:
                score += 7
        elif p == "r":
            f = sq % 8
            if wp_files[f] == 0 and bp_files[f] == 0:
                score -= 15
            elif bp_files[f] == 0:
                score -= 7
    return score


def _king_safety(board, ksq, own_pawn_files, color):
    if ksq is None:
        return 0
    f = ksq % 8
    shield = 0
    for nf in (f - 1, f, f + 1):
        if 0 <= nf <= 7 and own_pawn_files[nf] > 0:
            shield += 1
    return (shield - 3) * 12  # mancano pedoni davanti al re → penalità


# ----- Ordinamento delle mosse -----
def _is_capture(state, move):
    frm, to, promo = move
    if state.board[to] is not None:
        return True
    return state.board[frm].upper() == "P" and to == state.ep


def _order(ctx, state, moves, ply, tt_move):
    killers = ctx.killers.get(ply, ())
    board = state.board

    def key(move):
        if move == tt_move:
            return 10**9
        frm, to, promo = move
        victim = board[to]
        if victim is not None:
            return 10**6 + _VAL[victim.upper()] * 10 - _VAL[board[frm].upper()]
        if board[frm].upper() == "P" and to == state.ep:
            return 10**6 + _VAL["P"] * 10 - _VAL["P"]
        if promo:
            return 9 * 10**5 + _VAL[promo]
        if move in killers:
            return 8 * 10**5
        return ctx.history.get((frm, to), 0)

    return sorted(moves, key=key, reverse=True)


# ----- Quiescence -----
def _quiesce(ctx, state, alpha, beta, ply):
    ctx.tick()
    game = ctx.game
    in_check = game._in_check(state, state.current)
    if not in_check:
        stand = evaluate(state=state, game=game, ctx=ctx)
        if stand >= beta:
            return beta
        if stand > alpha:
            alpha = stand
        moves = [m for m in game.legal_moves(state) if _is_capture(state, m) or m[2]]
    else:
        moves = game.legal_moves(state)
        if not moves:
            return -(MATE - ply)  # matto

    for move in _order(ctx, state, moves, ply, None):
        score = -_quiesce(ctx, game.apply(state, move), -beta, -alpha, ply + 1)
        if score >= beta:
            return beta
        if score > alpha:
            alpha = score
    return alpha


# ----- Ricerca negamax con alpha-beta + TT -----
def _draw_score(ctx, state):
    """Valore della patta dal lato al tratto: l'IA (lato della radice) la evita se contempt>0."""
    return -ctx.contempt if state.current == ctx.root_side else ctx.contempt


def _negamax(ctx, state, depth, alpha, beta, ply):
    ctx.tick()
    game = ctx.game
    if state.halfmove >= 100 or game._insufficient(state.board):
        return _draw_score(ctx, state)

    key = (state.board, state.current, state.castling, state.ep)
    entry = ctx.tt.get(key)
    tt_move = None
    if entry is not None:
        e_depth, e_score, e_flag, e_move = entry
        tt_move = e_move
        if e_depth >= depth:
            if e_flag == 0:  # exact
                return e_score
            if e_flag == 1 and e_score > alpha:  # lower bound
                alpha = e_score
            elif e_flag == 2 and e_score < beta:  # upper bound
                beta = e_score
            if alpha >= beta:
                return e_score

    if depth <= 0:
        return _quiesce(ctx, state, alpha, beta, ply)

    moves = game.legal_moves(state)
    if not moves:
        if game._in_check(state, state.current):
            return -(MATE - ply)  # scacco matto
        return _draw_score(ctx, state)  # stallo

    alpha_orig = alpha
    best = -_INF
    best_move = None
    for move in _order(ctx, state, moves, ply, tt_move):
        score = -_negamax(ctx, game.apply(state, move), depth - 1, -beta, -alpha, ply + 1)
        if score > best:
            best = score
            best_move = move
        if best > alpha:
            alpha = best
        if alpha >= beta:
            if not _is_capture(state, move) and not move[2]:  # killer/history per mosse quiete
                ks = ctx.killers.setdefault(ply, [])
                if move not in ks:
                    ks.insert(0, move)
                    del ks[2:]
                k = (move[0], move[1])
                ctx.history[k] = ctx.history.get(k, 0) + depth * depth
            break

    flag = 0 if alpha_orig < best < beta else (1 if best >= beta else 2)
    ctx.tt[key] = (depth, best, flag, best_move)
    return best


def _search_root(ctx, state, depth, prev_best):
    game = ctx.game
    moves = game.legal_moves(state)
    if prev_best in moves:  # principal variation: prima la miglior mossa precedente
        moves = [prev_best] + [m for m in moves if m != prev_best]
    else:
        moves = _order(ctx, state, moves, 0, None)
    alpha = -_INF
    best = -_INF
    best_move = moves[0]
    for move in moves:
        score = -_negamax(ctx, game.apply(state, move), depth - 1, -_INF, -alpha, 1)
        # Jitter: piccola perturbazione SOLO alla radice per variare tra partite uguali;
        # trascurabile di fronte a differenze tattiche (un pezzo vale ≥ 300 cp).
        if ctx.jitter and best_move is not None:
            score += random.randint(-ctx.jitter, ctx.jitter)
        if score > best:
            best = score
            best_move = move
        if best > alpha:
            alpha = best
    return best, best_move


def best_move(game, state, history=None, time_limit=2.0, max_depth=64, style=None, jitter=0):
    """Sceglie la miglior mossa per il giocatore al tratto con iterative deepening.

    ``jitter`` (centipedoni) aggiunge una piccola casualità alla radice per variare tra
    partite (0 = deterministico, gioco più forte). Ritorna una mossa ``(from, to, promo)``
    legale, oppure ``None`` se non ce ne sono.
    """
    legal = game.legal_moves(state)
    if not legal:
        return None
    if len(legal) == 1:
        return legal[0]

    ctx = _Ctx(game=game, deadline=time.monotonic() + time_limit, jitter=max(0, int(jitter)))
    ctx.root_side = state.current
    if style:
        ctx.contempt = int(style.get("contempt", 0))
        ctx.aggression = float(style.get("aggression", 1.0))

    best = legal[0]
    for depth in range(1, max_depth + 1):
        ctx.allow_timeout = depth > 1  # la profondità 1 si completa sempre
        try:
            score, move = _search_root(ctx, state, depth, best)
        except TimeUp:
            break
        best = move
        if abs(score) >= MATE - 100:  # matto forzato trovato: inutile approfondire
            break
    return best
