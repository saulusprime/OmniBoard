"""Registro dei giochi disponibili nel motore."""

from __future__ import annotations

from ..backgammon.game import Backgammon
from ..chess.game import Chess
from ..connect4.game import Connect4
from ..draughts.game import Draughts
from ..tictactoe.game import TicTacToe
from .game import Game

_GAMES: dict[str, Game] = {
    game.code: game for game in [TicTacToe(), Connect4(), Draughts(), Chess(), Backgammon()]
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
