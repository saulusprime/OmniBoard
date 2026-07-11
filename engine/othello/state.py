"""Stato immutabile di una partita di Othello."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OthelloState:
    board: tuple  # 64 celle: 0 (Nero), 1 (Bianco) o None
    current: int
