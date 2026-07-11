"""Stato immutabile di una partita di Gomoku."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GomokuState:
    board: tuple  # 225 celle (15×15): 0 (Nero), 1 (Bianco) o None
    current: int
