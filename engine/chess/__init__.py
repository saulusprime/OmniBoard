"""Scacchi: regole (``game.py``), stato (``state.py``), scacchiera (``board.py``),
motore di ricerca (``engine.py``) e libro delle aperture (``openings.py``)."""

from .game import Chess
from .state import ChessState

__all__ = ["Chess", "ChessState"]
