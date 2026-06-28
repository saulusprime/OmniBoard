"""Motore di gioco astratto della piattaforma Scacchi.

Pacchetto Python puro: nessuna dipendenza da framework, rete o database.
"""

from .core import Game, Outcome, Player

__all__ = ["Game", "Outcome", "Player"]
