"""Stato immutabile di una partita di Dama italiana."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DraughtsState:
    board: tuple  # 64 celle: None oppure (player, king)
    current: int
