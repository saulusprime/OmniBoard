"""Stato immutabile di una partita di Tris."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TicTacToeState:
    board: tuple  # 9 celle: 0 (X), 1 (O) o None
    current: int  # giocatore di turno: 0 o 1
