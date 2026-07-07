"""Motore di ricerca per gli scacchi: molto più forte del minimax generico.

Tecniche implementate (tutte in puro Python, sopra le regole di ``game.py``):

- **Iterative deepening** con limite di tempo: il motore approfondisce la ricerca finché
  c'è tempo e restituisce sempre la miglior mossa dell'ultima profondità completata.
- **Alpha-beta** in forma negamax con **transposition table** (riconosce posizioni già
  analizzate, anche per trasposizione di mosse).
- **Quiescence search**: dalle foglie estende solo catture/promozioni (e tutte le mosse
  se sotto scacco) per evitare l'*horizon effect* (valutare una posizione a metà di uno
  scambio). È ciò che impedisce all'IA di "regalare" pezzi.
- **Ordinamento delle mosse**: mossa della TT, catture per MVV-LVA, promozioni, *killer
  moves* e *history heuristic* → molti più tagli alpha-beta, quindi più profondità.
- **PVS** (Principal Variation Search): solo la prima mossa di ogni nodo ha la finestra
  piena, le altre vengono sondate a finestra nulla e ri-cercate solo se promettono.
- **Aspiration windows** alla radice: dal terzo livello si cerca in una finestra stretta
  attorno al punteggio dell'iterazione precedente, riaprendola sul fail low/high.
- **SEE** (Static Exchange Evaluation): in quiescence le catture che PERDONO lo scambio
  completo (swap con raggi X) vengono potate; il delta pruning resta per il resto.
- **Futility pruning** ai nodi frontiera: a profondità 1, se la valutazione statica più
  un margine non raggiunge alpha, le mosse quiete che non danno scacco si saltano.
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

from .board import BISHOP_DIRS, BLACK, KNIGHT_DIRS, ROOK_DIRS, WHITE
from .context import SearchContext
from .errors import TimeUp
from .state import ChessState

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

# Tabelle precalcolate per carattere-pezzo: materiale+PST già col segno (Bianco positivo,
# Nero negativo e specchiato). Evita upper()/mirror per ogni pezzo a ogni valutazione.
_T_MID: dict = {}
for _k in "PNBRQ":
    _T_MID[_k] = [_VAL[_k] + _PST[_k][sq] for sq in range(64)]
    _T_MID[_k.lower()] = [-(_VAL[_k] + _PST[_k][_MIRROR[sq]]) for sq in range(64)]
_TK = {
    False: {  # mediogioco
        "K": list(_PST_K_MID),
        "k": [-_PST_K_MID[_MIRROR[sq]] for sq in range(64)],
    },
    True: {  # finale
        "K": list(_PST_K_END),
        "k": [-_PST_K_END[_MIRROR[sq]] for sq in range(64)],
    },
}
_VAL_C = {c: _VAL[c.upper()] for c in "PNBRQKpnbrqk"}


# ----- Valutazione -----
def _is_endgame(npm_w, npm_b):
    # Finale: poco materiale pesante per entrambi (≈ assenza di donne / pochi pezzi).
    return npm_w <= 1300 and npm_b <= 1300


def evaluate(game, state, ctx=None):
    """Valutazione statica dal punto di vista del giocatore al tratto (centipedoni).

    Un solo passaggio sulla scacchiera con tabelle precalcolate (materiale+PST già col
    segno); pedoni/torri/re raccolti al volo per struttura pedonale, colonne aperte e
    sicurezza del re.
    """
    board = state.board
    white = 0
    npm_w = npm_b = 0
    bishops_w = bishops_b = 0
    wp: list[int] = []
    bp: list[int] = []
    wr: list[int] = []
    br: list[int] = []
    wk = bk = wq = bq = None
    t = _T_MID
    for sq, p in enumerate(board):
        if p is None:
            continue
        if p == "P":
            wp.append(sq)
            white += t["P"][sq]
        elif p == "p":
            bp.append(sq)
            white += t["p"][sq]
        elif p == "K":
            wk = sq
        elif p == "k":
            bk = sq
        else:
            white += t[p][sq]
            if p.isupper():
                npm_w += _VAL_C[p]
                if p == "B":
                    bishops_w += 1
                elif p == "R":
                    wr.append(sq)
                elif p == "Q":
                    wq = sq
            else:
                npm_b += _VAL_C[p]
                if p == "b":
                    bishops_b += 1
                elif p == "r":
                    br.append(sq)
                elif p == "q":
                    bq = sq

    endgame = _is_endgame(npm_w, npm_b)
    tk = _TK[endgame]
    if wk is not None:
        white += tk["K"][wk]
    if bk is not None:
        white += tk["k"][bk]

    # Coppia degli alfieri.
    if bishops_w >= 2:
        white += 30
    if bishops_b >= 2:
        white -= 30

    # Sviluppo in apertura: sortita precoce della donna penalizzata finché i pezzi
    # minori sono ancora sulle case iniziali (principio classico di sviluppo).
    if not endgame:
        if wq is not None and wq != 59:
            und = (board[57] == "N") + (board[62] == "N") + (board[58] == "B") + (board[61] == "B")
            white -= 8 * und
        if bq is not None and bq != 3:
            und = (board[1] == "n") + (board[6] == "n") + (board[2] == "b") + (board[5] == "b")
            white += 8 * und

    wp_files = [0] * 8
    for sq in wp:
        wp_files[sq % 8] += 1
    bp_files = [0] * 8
    for sq in bp:
        bp_files[sq % 8] += 1

    white += _pawn_structure(wp, wp_files, bp_files, WHITE)
    white -= _pawn_structure(bp, bp_files, wp_files, 1 - WHITE)
    for sq in wr:
        f = sq % 8
        if wp_files[f] == 0:
            white += 15 if bp_files[f] == 0 else 7
    for sq in br:
        f = sq % 8
        if bp_files[f] == 0:
            white -= 15 if wp_files[f] == 0 else 7
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
            return 10**6 + _VAL_C[victim] * 10 - _VAL_C[board[frm]]
        if to == state.ep and board[frm] in ("P", "p"):
            return 10**6 + _VAL["P"] * 9
        if promo:
            return 9 * 10**5 + _VAL[promo]
        if move in killers:
            return 8 * 10**5
        return ctx.history.get((frm, to), 0)

    return sorted(moves, key=key, reverse=True)


# ----- SEE (Static Exchange Evaluation) -----
_RAYS = ROOK_DIRS + BISHOP_DIRS


def _least_attacker(occ, to, color):
    """(casa, pezzo) dell'attaccante di MINOR VALORE di ``color`` sulla casa ``to``.

    ``occ`` è l'occupazione corrente dello swap ({casa: pezzo}): rimuovere un
    pezzo e riscandire i raggi scopre naturalmente gli attacchi a raggi X.
    """
    tr, tc = divmod(to, 8)
    # Pedoni (i più economici): un pedone bianco attacca da una riga più in basso.
    pr = tr + 1 if color == WHITE else tr - 1
    pawn = "P" if color == WHITE else "p"
    if 0 <= pr < 8:
        for dc in (-1, 1):
            c = tc + dc
            if 0 <= c < 8 and occ.get(pr * 8 + c) == pawn:
                return pr * 8 + c, pawn
    knight = "N" if color == WHITE else "n"
    for dr, dc in KNIGHT_DIRS:
        r, c = tr + dr, tc + dc
        if 0 <= r < 8 and 0 <= c < 8 and occ.get(r * 8 + c) == knight:
            return r * 8 + c, knight
    best = None
    for dr, dc in _RAYS:
        r, c, dist = tr + dr, tc + dc, 1
        diag = dr != 0 and dc != 0
        while 0 <= r < 8 and 0 <= c < 8:
            piece = occ.get(r * 8 + c)
            if piece is not None:
                if (piece.isupper()) == (color == WHITE):
                    up = piece.upper()
                    if (
                        up == "Q"
                        or (up == "B" and diag)
                        or (up == "R" and not diag)
                        or (up == "K" and dist == 1)
                    ):
                        if best is None or _VAL_C[piece] < _VAL_C[best[1]]:
                            best = (r * 8 + c, piece)
                break  # il primo pezzo sul raggio blocca comunque
            r += dr
            c += dc
            dist += 1
    return best


def _see(board, move):
    """Valore dello SCAMBIO COMPLETO sulla casa di arrivo (swap algorithm).

    Simula la sequenza di ricatture con l'attaccante di minor valore a ogni
    turno (raggi X inclusi, perché i raggi vengono riscanditi dopo ogni
    rimozione) e con il passaggio all'indietro che permette a ciascun lato di
    FERMARSI quando ricatturare non conviene. Usata in quiescence per potare
    le catture perdenti (es. DxP difeso da pedone → ~ -800). L'en passant e le
    promozioni non passano da qui (rare: si lasciano al delta pruning).
    """
    frm, to, _promo = move
    victim = board[to]
    if victim is None:
        return 0
    occ = {sq: p for sq, p in enumerate(board) if p is not None}
    attacker = occ.pop(frm)
    gain = [_VAL_C[victim]]
    occ[to] = attacker
    side = BLACK if attacker.isupper() else WHITE  # tocca ricatturare all'altro
    while True:
        nxt = _least_attacker(occ, to, side)
        if nxt is None:
            break
        sq, piece = nxt
        if piece.upper() == "K":
            # Il re può ricatturare solo se la casa non resta difesa (altrimenti
            # la "ricattura" sarebbe illegale e falserebbe lo scambio).
            probe = dict(occ)
            del probe[sq]
            if _least_attacker(probe, to, 1 - side) is not None:
                break
        gain.append(_VAL_C[occ[to]] - gain[-1])
        del occ[sq]
        occ[to] = piece
        side = 1 - side
    for i in range(len(gain) - 1, 0, -1):
        gain[i - 1] = -max(-gain[i - 1], gain[i])
    return gain[0]


# ----- Quiescence -----
_DELTA_MARGIN = 200  # margine di sicurezza per il delta pruning (centipedoni)


def _quiesce(ctx, state, alpha, beta, ply):
    """Ricerca di quiete su **pseudo-mosse** (legalità verificata dopo l'applicazione:
    una mossa che lascia il proprio re sotto attacco viene scartata). Evita così il
    doppio lavoro di ``legal_moves`` (che applica ogni mossa una volta in più)."""
    ctx.tick()
    game = ctx.game
    board = state.board
    color = state.current
    in_check = game._in_check(state, color)
    if in_check:
        moves = game._pseudo_moves(state)  # sotto scacco: tutte le evasioni
    else:
        stand = evaluate(game, state, ctx)
        if stand >= beta:
            return beta
        if stand > alpha:
            alpha = stand
        moves = game._capture_moves(state)  # solo catture/promozioni/en passant
        moves.sort(  # MVV-LVA leggero
            key=lambda m: (_VAL_C.get(board[m[1]], 100)) * 10 - _VAL_C[board[m[0]]],
            reverse=True,
        )

    searched = 0
    for move in moves:
        if not in_check:
            # Delta pruning: se nemmeno catturando il pezzo (con margine) si arriva ad
            # alpha, inutile esplorare la cattura.
            victim = board[move[1]]
            gain = _VAL_C[victim] if victim is not None else _VAL["P"]
            if move[2]:
                gain += _VAL[move[2]] - _VAL["P"]
            if stand + gain + _DELTA_MARGIN <= alpha:
                continue
            # SEE: la cattura che PERDE lo scambio completo (es. donna per pedone
            # difeso) non merita la ricerca — è il grosso del ramo di quiete.
            if victim is not None and not move[2] and _see(board, move) < 0:
                continue
        child = game.apply(state, move)
        if game._in_check(child, color):
            continue  # pseudo-mossa illegale
        searched += 1
        score = -_quiesce(ctx, child, -beta, -alpha, ply + 1)
        if score >= beta:
            return beta
        if score > alpha:
            alpha = score

    if in_check and searched == 0:
        return -(MATE - ply)  # nessuna evasione legale: matto
    return alpha


# ----- Ricerca negamax con alpha-beta + TT -----
def _draw_score(ctx, state):
    """Valore della patta dal lato al tratto: l'IA (lato della radice) la evita se contempt>0."""
    return -ctx.contempt if state.current == ctx.root_side else ctx.contempt


_MATE_BOUND = MATE - 1000


def _to_tt(score, ply):
    """I punteggi di matto sono relativi alla radice: si normalizzano al nodo per la TT."""
    if score >= _MATE_BOUND:
        return score + ply
    if score <= -_MATE_BOUND:
        return score - ply
    return score


def _from_tt(score, ply):
    if score >= _MATE_BOUND:
        return score - ply
    if score <= -_MATE_BOUND:
        return score + ply
    return score


def _has_pieces(state):
    """True se il lato al tratto ha almeno un pezzo oltre a re e pedoni (guardia
    anti-zugzwang per il null-move pruning)."""
    majors = "QRBN" if state.current == WHITE else "qrbn"
    return any(p in majors for p in state.board if p)


def _negamax(ctx, state, depth, alpha, beta, ply):
    ctx.tick()
    game = ctx.game
    if state.halfmove >= 100 or game._insufficient(state.board):
        return _draw_score(ctx, state)

    key = (state.board, state.current, state.castling, state.ep)
    # Anti-ripetizione: tornare a una posizione già vista nella partita vale come patta
    # (evita il "rimescolamento" senza scopo e spinge il motore a fare progressi).
    if ply and key in ctx.past_keys:
        return _draw_score(ctx, state)

    color = state.current
    in_check = game._in_check(state, color)
    if in_check:
        depth += 1  # estensione di scacco: le sequenze forzate vengono risolte

    entry = ctx.tt.get(key)
    tt_move = None
    if entry is not None:
        e_depth, e_score, e_flag, e_move = entry
        tt_move = e_move
        if e_depth >= depth:
            e_score = _from_tt(e_score, ply)
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

    # Null-move pruning: se anche "passando" la posizione resta ≥ beta, si taglia.
    # Evitato sotto scacco, vicino ai matti e nei finali di soli pedoni (zugzwang).
    if depth >= 3 and ply and not in_check and beta < _MATE_BOUND and _has_pieces(state):
        null = ChessState(
            board=state.board,
            current=1 - color,
            castling=state.castling,
            ep=None,
            halfmove=state.halfmove + 1,
        )
        if -_negamax(ctx, null, depth - 3, -beta, -beta + 1, ply + 1) >= beta:
            return beta

    # Futility pruning ai nodi FRONTIERA (depth 1): se la valutazione statica più
    # un margine non arriva ad alpha, le mosse quiete non possono recuperare in una
    # sola mossa → si saltano (le catture, le promozioni e gli scacchi no).
    futile = False
    static = None
    if depth == 1 and not in_check and abs(alpha) < _MATE_BOUND:
        static = evaluate(game, state, ctx)
        futile = static + 150 <= alpha

    alpha_orig = alpha
    best = -_INF
    best_move = None
    searched = 0
    # Pseudo-mosse: la legalità si verifica dopo l'applicazione (il re resta sotto
    # attacco → scartata). Si evita così il doppio ``apply`` di ``legal_moves``.
    for move in _order(ctx, state, game._pseudo_moves(state), ply, tt_move):
        child = game.apply(state, move)
        if game._in_check(child, color):
            continue
        searched += 1
        quiet = not move[2] and not _is_capture(state, move)
        # Futility: la PRIMA mossa legale si cerca sempre (serve per matto/stallo e
        # come miglior mossa di riserva); le quiete successive che non danno scacco
        # vengono saltate col punteggio statico come limite superiore.
        if futile and quiet and searched > 1 and not game._in_check(child, 1 - color):
            if static > best:
                best = static
            continue
        # PVS (Principal Variation Search): solo la prima mossa ha la finestra piena;
        # le altre si sondano con finestra nulla — con LMR anche ridotte di un livello
        # se quiete e tardive — e si ri-cercano per intero solo se promettono.
        if searched == 1:
            score = -_negamax(ctx, child, depth - 1, -beta, -alpha, ply + 1)
        else:
            reduction = 1 if (searched > 3 and depth >= 3 and not in_check and quiet) else 0
            score = -_negamax(ctx, child, depth - 1 - reduction, -alpha - 1, -alpha, ply + 1)
            if score > alpha and reduction:
                # La riduzione prometteva: si verifica a profondità piena (finestra nulla).
                score = -_negamax(ctx, child, depth - 1, -alpha - 1, -alpha, ply + 1)
            if alpha < score < beta:
                # Supera alpha dentro la finestra: ricerca piena per il valore esatto.
                score = -_negamax(ctx, child, depth - 1, -beta, -alpha, ply + 1)
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
                ctx.history[k] = min(500_000, ctx.history.get(k, 0) + depth * depth)
            break

    if searched == 0:
        return -(MATE - ply) if in_check else _draw_score(ctx, state)  # matto / stallo

    flag = 0 if alpha_orig < best < beta else (1 if best >= beta else 2)
    ctx.tt[key] = (depth, _to_tt(best, ply), flag, best_move)
    return best


def _search_root(ctx, state, depth, prev_best, alpha0=-_INF, beta0=_INF):
    """Ricerca alla radice dentro la finestra [alpha0, beta0] (aspiration window).

    PVS anche qui: prima mossa a finestra piena, le altre sondate a finestra
    nulla e ri-cercate solo se promettono. Il chiamante riconosce il fail
    low/high (best ≤ alpha0 / best ≥ beta0) e riapre la finestra.
    """
    game = ctx.game
    moves = game.legal_moves(state)
    if prev_best in moves:  # principal variation: prima la miglior mossa precedente
        moves = [prev_best] + [m for m in moves if m != prev_best]
    else:
        moves = _order(ctx, state, moves, 0, None)
    alpha = alpha0
    best = -_INF
    best_move = moves[0]
    scored = []
    for n, move in enumerate(moves):
        child = game.apply(state, move)
        if n == 0:
            score = -_negamax(ctx, child, depth - 1, -beta0, -alpha, 1)
        else:
            score = -_negamax(ctx, child, depth - 1, -alpha - 1, -alpha, 1)
            if alpha < score < beta0:
                score = -_negamax(ctx, child, depth - 1, -beta0, -alpha, 1)
        scored.append((score, move))
        if score > best:
            best = score
            best_move = move
        if best > alpha:
            alpha = best
        if alpha >= beta0:
            break  # fail high: la finestra va riaperta dal chiamante
    # Jitter: scelta casuale tra le mosse quasi-ottimali (entro `jitter` centipedoni dal
    # massimo) per variare tra partite. La ricerca resta esatta: il jitter non tocca
    # alpha né i punteggi, quindi non degrada la qualità tattica.
    if ctx.jitter:
        near_best = [m for s, m in scored if s >= best - ctx.jitter]
        if near_best:
            best_move = random.choice(near_best)
    return best, best_move


def _past_position_keys(game, state, history):
    """Chiavi delle posizioni già occorse nella partita, ricostruite dallo storico UCI.

    Se lo storico non riproduce lo stato attuale (es. posizione caricata da FEN), si
    rinuncia all'anti-ripetizione e si ritorna l'insieme vuoto.
    """
    if not history:
        return frozenset()
    s = game.initial_state()
    keys = set()
    for uci in history:
        keys.add((s.board, s.current, s.castling, s.ep))
        move = next((m for m in game._pseudo_moves(s) if game.move_id(m) == uci), None)
        if move is None:
            return frozenset()
        s = game.apply(s, move)
    if s.board != state.board or s.current != state.current:
        return frozenset()
    return frozenset(keys)


def best_move(game, state, history=None, time_limit=2.0, max_depth=64, style=None, jitter=0):
    """Sceglie la miglior mossa per il giocatore al tratto con iterative deepening.

    ``jitter`` (centipedoni) sceglie a caso tra le mosse quasi-ottimali alla radice per
    variare tra partite (0 = deterministico). Ritorna una mossa ``(from, to, promo)``
    legale, oppure ``None`` se non ce ne sono.
    """
    legal = game.legal_moves(state)
    if not legal:
        return None
    if len(legal) == 1:
        return legal[0]

    ctx = SearchContext(
        game=game, deadline=time.monotonic() + time_limit, jitter=max(0, int(jitter))
    )
    ctx.root_side = state.current
    ctx.past_keys = _past_position_keys(game, state, history)
    if style:
        ctx.contempt = int(style.get("contempt", 0))
        ctx.aggression = float(style.get("aggression", 1.0))

    best = legal[0]
    prev_score = None
    window = 50  # ampiezza iniziale dell'aspiration window (centipedoni)
    for depth in range(1, max_depth + 1):
        ctx.allow_timeout = depth > 1  # la profondità 1 si completa sempre
        try:
            # Aspiration window: dal terzo livello si cerca in una finestra stretta
            # attorno al punteggio precedente (molti più tagli); se il risultato
            # esce dalla finestra (fail low/high) si ri-cerca a finestra piena.
            if depth >= 3 and prev_score is not None and abs(prev_score) < _MATE_BOUND:
                a, b = prev_score - window, prev_score + window
                score, move = _search_root(ctx, state, depth, best, a, b)
                if score <= a or score >= b:
                    score, move = _search_root(ctx, state, depth, best)
            else:
                score, move = _search_root(ctx, state, depth, best)
        except TimeUp:
            break
        best = move
        prev_score = score
        if abs(score) >= MATE - 100:  # matto forzato trovato: inutile approfondire
            break
    return best
