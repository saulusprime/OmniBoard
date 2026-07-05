"""Stato immutabile di una partita di scacchi."""

from __future__ import annotations

from typing import NamedTuple


class ChessState(NamedTuple):
    # NamedTuple (non dataclass frozen): l'istanziazione è molto più veloce e `apply`
    # ne crea una per ogni nodo di ricerca del motore.
    board: tuple
    current: int
    castling: tuple  # (wK, wQ, bK, bQ)
    ep: int | None  # casa bersaglio dell'en passant
    halfmove: int  # contatore per la regola delle 50 mosse
