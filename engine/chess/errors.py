"""Eccezioni del motore di ricerca degli scacchi."""

from __future__ import annotations


class TimeUp(Exception):
    """Sollevata internamente quando scade il budget di tempo della ricerca."""
