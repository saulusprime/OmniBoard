"""Stato immutabile di una partita di Forza 4."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Connect4State:
    board: tuple  # 42 celle: 0, 1 o None (riga 0 in alto)
    current: int
