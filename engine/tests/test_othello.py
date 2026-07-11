"""Test del gioco Othello."""

import random

import pytest

from engine.othello import Othello, OthelloState


def test_initial_state_and_opening_moves():
    game = Othello()
    state = game.initial_state()
    assert state.current == 0  # il Nero muove per primo
    assert state.board[27] == 1 and state.board[36] == 1  # d4, e5 Bianco
    assert state.board[28] == 0 and state.board[35] == 0  # e4, d5 Nero
    assert sorted(game.legal_moves(state)) == [19, 26, 37, 44]  # d3, c4, f5, e6
    assert not game.is_terminal(state)


def test_apply_flips_the_bracketed_line():
    game = Othello()
    state = game.apply(game.initial_state(), 19)  # Nero in d3 gira d4
    assert state.board[19] == 0 and state.board[27] == 0
    assert state.current == 1
    assert game.view_status(state) == "● 4 — ○ 1"


def test_illegal_moves_are_rejected():
    game = Othello()
    state = game.initial_state()
    with pytest.raises(ValueError):
        game.apply(state, 0)  # non gira nulla
    with pytest.raises(ValueError):
        game.apply(state, 27)  # casella occupata
    with pytest.raises(ValueError):
        game.apply(state, 64)  # fuori dalla scacchiera


def test_automatic_pass_keeps_the_turn():
    """Se dopo la mossa l'avversario non ha giocate, il tratto resta a chi ha mosso."""
    game = Othello()
    board = [None] * 64
    board[0], board[1], board[3] = 0, 1, 1  # ● ○ _ ○ sulla prima traversa
    state = OthelloState(board=tuple(board), current=0)
    after = game.apply(state, 2)  # gira b1; il Bianco non ha mosse, il Nero sì
    assert after.board[1] == 0
    assert after.current == 0  # passo automatico del Bianco
    final = game.apply(after, 4)  # gira d1: nessuno può più muovere
    assert game.is_terminal(final)
    assert game.outcome(final).winner == 0  # 5-0


def test_random_game_reaches_a_verdict():
    game = Othello()
    random.seed(11)
    state = game.initial_state()
    for _ in range(200):
        if game.is_terminal(state):
            break
        state = game.apply(state, random.choice(game.legal_moves(state)))
    assert game.is_terminal(state)
    blacks = sum(1 for v in state.board if v == 0)
    whites = sum(1 for v in state.board if v == 1)
    expected = None if blacks == whites else (0 if blacks > whites else 1)
    assert game.outcome(state).winner == expected


def test_view_board_uses_disc_glyphs():
    game = Othello()
    view = game.view_board(game.initial_state())
    assert view[28] == "●" and view[27] == "○"
    assert game.describe_move(game.initial_state(), 19) == "d3"


def test_local_ai_beats_random():
    """Il minimax generico (profondità 4 + euristica posizionale) domina il caso."""
    from app.opponents.local import best_move

    game = Othello()
    random.seed(7)
    state = game.initial_state()
    while not game.is_terminal(state):
        if state.current == 0:
            move, _src = best_move(game, state, game.legal_moves(state))
        else:
            move = random.choice(game.legal_moves(state))
        state = game.apply(state, move)
    assert game.outcome(state).winner == 0
