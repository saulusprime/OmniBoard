"""Motore di gioco astratto della piattaforma Scacchi.

Pacchetto Python puro: nessuna dipendenza da framework, rete o database.
Struttura: ``common/`` (interfaccia, esito, registro) + una directory per gioco
(``tictactoe/``, ``connect4/``, ``draughts/``, ``chess/``), una classe per file.
"""

from .common.game import Game
from .common.outcome import Outcome, Player
from .common.registry import available_games, get_game, is_playable

__all__ = ["Game", "Outcome", "Player", "get_game", "is_playable", "available_games"]
