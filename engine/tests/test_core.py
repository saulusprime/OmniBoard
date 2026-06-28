"""Test dell'interfaccia astratta del motore."""

import pytest

from engine import Game, Outcome


def test_outcome_winner():
    assert Outcome(winner=None).winner is None
    assert Outcome(winner=0).winner == 0


def test_game_is_abstract():
    with pytest.raises(TypeError):
        Game()


def test_minimal_concrete_game():
    """Un gioco minimo implementa l'interfaccia e arriva a uno stato terminale."""

    class Tiny(Game):
        code = "tiny"
        name = "Tiny"

        def initial_state(self):
            return 0

        def current_player(self, state):
            return state % 2

        def legal_moves(self, state):
            return [] if state >= 2 else [1]

        def apply(self, state, move):
            return state + move

        def is_terminal(self, state):
            return state >= 2

        def outcome(self, state):
            return Outcome(winner=0)

    game = Tiny()
    state = game.initial_state()
    assert not game.is_terminal(state)
    assert game.is_chance_node(state) is False

    state = game.apply(state, game.legal_moves(state)[0])
    state = game.apply(state, 1)

    assert game.is_terminal(state)
    assert game.legal_moves(state) == []
    assert game.outcome(state).winner == 0
