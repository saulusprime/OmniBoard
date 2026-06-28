"""Registro dei giochi disponibili nel motore."""

from __future__ import annotations

from .core import Game
from .games.chess import Chess
from .games.connect4 import Connect4
from .games.draughts import Draughts
from .games.tictactoe import TicTacToe

_GAMES: dict[str, Game] = {
    game.code: game for game in [TicTacToe(), Connect4(), Draughts(), Chess()]
}


def get_game(code: str) -> Game:
    """Restituisce l'istanza del gioco; solleva KeyError se non implementato."""
    if code not in _GAMES:
        raise KeyError(code)
    return _GAMES[code]


def is_playable(code: str) -> bool:
    return code in _GAMES


def available_games() -> list[Game]:
    return list(_GAMES.values())
