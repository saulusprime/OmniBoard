"""Contesto di ricerca del motore degli scacchi.

Raccoglie tutto lo stato condiviso di una ricerca (transposition table, killer moves,
history heuristic, budget di tempo, parametri di stile) così che le funzioni di
``engine.py`` restino pure e senza stato globale.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .errors import TimeUp


@dataclass
class SearchContext:
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
    past_keys: frozenset = frozenset()  # posizioni già occorse nella partita (anti-ripetizione)

    def tick(self):
        self.nodes += 1
        if self.allow_timeout and (self.nodes & 1023) == 0 and time.monotonic() > self.deadline:
            raise TimeUp
