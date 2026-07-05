"""Esito di una partita terminata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

Player = int  # due giocatori: 0 e 1


@dataclass(frozen=True)
class Outcome:
    """Esito di una partita terminata. ``winner`` None indica una patta."""

    winner: Optional[Player]
