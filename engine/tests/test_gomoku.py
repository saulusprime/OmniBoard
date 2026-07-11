"""Test del gioco Gomoku e del suo motore dedicato."""

import random
import time

import pytest

from engine.gomoku import COLS, Gomoku


def _play(game, moves):
    state = game.initial_state()
    for m in moves:
        state = game.apply(state, m)
    return state


def test_initial_state_and_basic_rules():
    game = Gomoku()
    state = game.initial_state()
    assert state.current == 0  # il Nero muove per primo
    assert len(game.legal_moves(state)) == 225
    state = game.apply(state, 112)  # centro (h8)
    assert state.board[112] == 0 and state.current == 1
    assert game.describe_move(game.initial_state(), 112) == "h8"
    with pytest.raises(ValueError):
        game.apply(state, 112)  # intersezione occupata


def test_five_in_a_row_wins_and_overline_counts():
    game = Gomoku()
    # Nero: 5 orizzontali consecutive (freestyle: vale anche l'overline).
    state = _play(game, [112, 0, 113, 1, 114, 2, 115, 3, 116])
    assert game.is_terminal(state)
    assert game.outcome(state).winner == 0
    # Overline: sei di fila vincono comunque (mosse bianche sparse, mai in fila).
    state = _play(game, [110, 0, 111, 1, 112, 2, 113, 20, 115, 40, 114])
    assert game.is_terminal(state)
    assert game.outcome(state).winner == 0


def test_engine_first_move_is_center():
    game = Gomoku()
    assert game.engine_move(game.initial_state(), time_limit=0.3) == 112


def test_engine_takes_the_winning_point():
    game = Gomoku()
    state = _play(game, [112, 0, 113, 1, 114, 2, 115, 3])  # Nero ha quattro in fila
    move = game.engine_move(state, time_limit=0.3)
    assert move in (111, 116)


def test_engine_blocks_the_open_four():
    game = Gomoku()
    # Tocca al Bianco: il quattro aperto del Nero va tamponato (partita comunque
    # compromessa, ma il blocco è l'unica resistenza).
    state = _play(game, [112, 0, 113, 1, 114, 2, 115])
    move = game.engine_move(state, time_limit=0.3)
    assert move in (111, 116)


def test_engine_converts_the_open_three():
    """Tre aperto col tratto = vittoria forzata: il motore estende a quattro aperto."""
    game = Gomoku()
    # Dopo 6 semimosse tocca al Nero, che ha il tre aperto 112-114: l'estensione
    # (111 o 115) crea il quattro aperto, indifendibile.
    state = _play(game, [112, 0, 113, 1, 114, 2])
    move = game.engine_move(state, time_limit=0.5)
    assert move in (111, 115)


def test_engine_returns_quick_legal_move_midgame():
    game = Gomoku()
    random.seed(3)
    state = game.initial_state()
    for _ in range(20):
        state = game.apply(state, random.choice(game.legal_moves(state)))
    t0 = time.monotonic()
    move = game.engine_move(state, time_limit=0.5)
    assert time.monotonic() - t0 < 2.0
    assert move in game.legal_moves(state)


def test_local_player_uses_dedicated_engine():
    from app.opponents.local import best_move

    game = Gomoku()
    state = game.initial_state()
    move, source = best_move(game, state, game.legal_moves(state), think_ms=200)
    assert source == "engine"
    assert 0 <= move < 15 * COLS
