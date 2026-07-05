"""Parti comuni del motore: interfaccia astratta dei giochi, esito, registro."""

from .game import Game
from .outcome import Outcome, Player
from .registry import available_games, get_game, is_playable

__all__ = ["Game", "Outcome", "Player", "available_games", "get_game", "is_playable"]
