"""Test del gioco Forza 4."""

import pytest

from engine.connect4 import COLS, ROWS, Connect4
from engine.connect4.game import _index


def test_initial_state():
    game = Connect4()
    state = game.initial_state()
    assert game.current_player(state) == 0
    assert game.legal_moves(state) == list(range(COLS))
    assert not game.is_terminal(state)
    assert len(state.board) == ROWS * COLS


def test_drop_stacks_from_bottom():
    game = Connect4()
    state = game.apply(game.initial_state(), 3)  # X nella colonna 3
    assert state.board[_index(ROWS - 1, 3)] == 0  # cade in basso
    assert game.current_player(state) == 1
    state = game.apply(state, 3)  # O sopra la X
    assert state.board[_index(ROWS - 2, 3)] == 1


def test_vertical_win():
    game = Connect4()
    state = game.initial_state()
    for move in [0, 1, 0, 1, 0, 1, 0]:  # X impila 4 nella colonna 0
        state = game.apply(state, move)
    assert game.is_terminal(state)
    assert game.outcome(state).winner == 0


def test_full_column_is_illegal():
    game = Connect4()
    state = game.initial_state()
    for _ in range(ROWS):  # riempie la colonna 0
        state = game.apply(state, 0)
    assert 0 not in game.legal_moves(state)
    with pytest.raises(ValueError):
        game.apply(state, 0)


def test_describe_move_is_1_based_column():
    game = Connect4()
    state = game.initial_state()
    assert game.describe_move(state, 0) == "1"
    assert game.describe_move(state, 6) == "7"


def test_serialize_roundtrip():
    game = Connect4()
    state = game.apply(game.initial_state(), 3)
    assert game.deserialize_state(game.serialize_state(state)) == state
