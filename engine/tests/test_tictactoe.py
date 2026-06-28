"""Test del gioco Tris."""

import pytest

from engine.games.tictactoe import TicTacToe


def test_initial_state():
    game = TicTacToe()
    state = game.initial_state()
    assert game.current_player(state) == 0
    assert len(game.legal_moves(state)) == 9
    assert not game.is_terminal(state)


def test_apply_is_immutable_and_switches_player():
    game = TicTacToe()
    state = game.initial_state()
    new_state = game.apply(state, 4)
    assert new_state.board[4] == 0
    assert game.current_player(new_state) == 1
    assert state.board[4] is None  # lo stato originale non cambia


def test_illegal_move_raises():
    game = TicTacToe()
    state = game.apply(game.initial_state(), 0)
    with pytest.raises(ValueError):
        game.apply(state, 0)  # casella occupata


def test_row_win():
    game = TicTacToe()
    state = game.initial_state()
    for move in [0, 3, 1, 4, 2]:  # X: 0,1,2 (riga in alto) -> vince X
        state = game.apply(state, move)
    assert game.is_terminal(state)
    assert game.outcome(state).winner == 0
    assert game.legal_moves(state) == []


def test_draw():
    game = TicTacToe()
    state = game.initial_state()
    for move in [0, 1, 2, 4, 3, 5, 7, 6, 8]:
        state = game.apply(state, move)
    assert game.is_terminal(state)
    assert game.outcome(state).winner is None


def test_serialize_roundtrip():
    game = TicTacToe()
    state = game.apply(game.initial_state(), 4)
    restored = game.deserialize_state(game.serialize_state(state))
    assert restored == state


def test_describe_move_notation():
    game = TicTacToe()
    state = game.initial_state()
    assert game.describe_move(state, 0) == "a1"
    assert game.describe_move(state, 4) == "b2"
    assert game.describe_move(state, 8) == "c3"
