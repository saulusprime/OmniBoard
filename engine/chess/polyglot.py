"""Libro di aperture in formato Polyglot (.bin): hash Zobrist e probing.

Il formato Polyglot indicizza le posizioni con una chiave Zobrist a 64 bit
calcolata con la tabella standard ``RANDOM64`` (vedi polyglot_data.py). Ogni
voce del file è di 16 byte big-endian: chiave (8) + mossa (2) + peso (2) +
learn (4), e il file è ORDINATO per chiave: il probing è una ricerca binaria.

Regole di hashing della specifica:

- pezzo: offset ``64·kind + 8·riga + colonna`` con kind = {pedone nero 0,
  pedone bianco 1, cavallo nero 2, … re bianco 11} e riga 0 = prima traversa;
- arrocco (768-771): un termine per ogni diritto residuo;
- en passant (772-779, per colonna): SOLO se un pedone del giocatore al tratto
  può effettivamente catturare al varco (adiacente alla casa bersaglio);
- tratto (780): sommato se muove il bianco.

La mossa è impacchettata a bit (colonna/riga di arrivo e partenza, promozione);
gli arrocchi sono scritti come «re cattura la propria torre» (e1h1, e8a8, …) e
qui vengono tradotti nella nostra notazione UCI (e1g1, e8c8, …).
"""

from __future__ import annotations

import bisect
import os
import random
import struct

from .polyglot_data import RANDOM64

_PROMO = ["", "n", "b", "r", "q"]  # codifica Polyglot della promozione (0 = nessuna)

# Traduzione degli arrocchi: «re cattura torre» → mossa di re di due case.
_CASTLE = {"e1h1": "e1g1", "e1a1": "e1c1", "e8h8": "e8g8", "e8a8": "e8c8"}

# Cache dei libri caricati: {percorso: (chiavi ordinate, righe grezze)}.
_books: dict[str, tuple[list[int], bytes]] = {}


def reset_cache() -> None:
    _books.clear()


def _kind(piece: str) -> int:
    """Indice Polyglot del pezzo: 2·tipo + colore (bianco = +1)."""
    order = "pnbrqk"
    return 2 * order.index(piece.lower()) + (1 if piece.isupper() else 0)


def zobrist_key(state) -> int:
    """Chiave Polyglot della posizione (board con riga 0 = ottava traversa)."""
    key = 0
    for sq, piece in enumerate(state.board):
        if piece is None:
            continue
        row = 7 - (sq // 8)  # Polyglot conta dalla prima traversa
        col = sq % 8
        key ^= RANDOM64[64 * _kind(piece) + 8 * row + col]
    wk, wq, bk, bq = state.castling
    for has_right, offset in ((wk, 768), (wq, 769), (bk, 770), (bq, 771)):
        if has_right:
            key ^= RANDOM64[offset]
    if state.ep is not None:
        # L'en passant si somma SOLO se c'è davvero un pedone del giocatore al
        # tratto pronto a catturare (adiacente alla casa bersaglio).
        col = state.ep % 8
        pawn, row = ("P", 3) if state.current == 0 else ("p", 4)  # riga interna (0 = ottava)
        for dc in (-1, 1):
            if 0 <= col + dc < 8 and state.board[row * 8 + col + dc] == pawn:
                key ^= RANDOM64[772 + col]
                break
    if state.current == 0:  # muove il bianco
        key ^= RANDOM64[780]
    return key


def _decode_move(raw: int) -> str:
    to_col, to_row = raw & 7, (raw >> 3) & 7
    from_col, from_row = (raw >> 6) & 7, (raw >> 9) & 7
    promo = _PROMO[(raw >> 12) & 7]
    uci = f"{chr(ord('a') + from_col)}{from_row + 1}{chr(ord('a') + to_col)}{to_row + 1}{promo}"
    return _CASTLE.get(uci, uci)


def _load(path: str) -> tuple[list[int], bytes]:
    """Carica e memoizza il libro: chiavi (per bisect) + byte grezzi delle voci."""
    if path not in _books:
        with open(path, "rb") as f:
            data = f.read()
        data = data[: len(data) - len(data) % 16]  # tronca eventuali byte spuri in coda
        keys = [struct.unpack_from(">Q", data, i)[0] for i in range(0, len(data), 16)]
        _books[path] = (keys, data)
    return _books[path]


def probe(state, path: str | None = None) -> list[tuple[str, int]]:
    """Le mosse del libro per la posizione: [(uci, peso), …] (vuoto se assente).

    ``path`` di default viene da ``CHESS_POLYGLOT_BOOK``; errori di I/O o file
    malformati producono semplicemente un libro vuoto (il gioco non si ferma).
    """
    path = path or os.getenv("CHESS_POLYGLOT_BOOK")
    if not path:
        return []
    try:
        keys, data = _load(path)
    except OSError:
        return []
    key = zobrist_key(state)
    out: list[tuple[str, int]] = []
    i = bisect.bisect_left(keys, key)
    while i < len(keys) and keys[i] == key:
        _, raw_move, weight = struct.unpack_from(">QHH", data, i * 16)
        out.append((_decode_move(raw_move), weight))
        i += 1
    return out


def weighted_choice(entries: list[tuple[str, int]]) -> str | None:
    """Scelta proporzionale al peso (pesi tutti nulli → scelta uniforme)."""
    if not entries:
        return None
    total = sum(w for _, w in entries)
    if total <= 0:
        return random.choice(entries)[0]
    pick = random.randrange(total)
    for uci, weight in entries:
        pick -= weight
        if pick < 0:
            return uci
    return entries[-1][0]  # non raggiungibile, difesa
