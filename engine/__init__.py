"""Motore di gioco astratto della piattaforma Scacchi.

Pacchetto Python puro: nessuna dipendenza da framework, rete o database.
"""

from .core import Game, Outcome, Player
from .registry import available_games, get_game, is_playable

__all__ = ["Game", "Outcome", "Player", "get_game", "is_playable", "available_games"]
