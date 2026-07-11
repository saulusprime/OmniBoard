"""Test del gioco Forza 4 e del suo motore dedicato (bitboard)."""

import time

import pytest

from engine.connect4 import COLS, ROWS, Connect4
from engine.connect4 import engine as c4_engine
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


# ----- Motore dedicato (bitboard + negamax iterativo) -----


def test_bitboard_conversion_matches_rules():
    """Su una partita scriptata i bitboard rispecchiano stato, conteggi e vittorie."""
    game = Connect4()
    state = game.initial_state()
    for move in [3, 3, 2, 4, 4, 2, 5, 1, 2, 2, 6, 0, 1, 5]:
        state = game.apply(state, move)
        position, mask = c4_engine.from_state(state)
        assert mask.bit_count() == sum(1 for c in state.board if c is not None)
        assert position.bit_count() == sum(1 for c in state.board if c == state.current)
        # Chi ha appena mosso è l'avversario di chi muove: la vittoria è sua o di nessuno.
        just_moved_won = c4_engine._has_won(position ^ mask)
        winner = game.outcome(state).winner if game.is_terminal(state) else None
        assert just_moved_won == (winner == 1 - state.current)


def test_engine_takes_immediate_win():
    game = Connect4()
    state = game.initial_state()
    for move in [0, 1, 0, 1, 0, 2]:  # X ha tre pedine in colonna 0, tocca a X
        state = game.apply(state, move)
    assert game.engine_move(state, time_limit=0.2) == 0


def test_engine_blocks_immediate_threat():
    game = Connect4()
    state = game.initial_state()
    for move in [0, 1, 0, 2, 0]:  # X minaccia in colonna 0, tocca a O
        state = game.apply(state, move)
    assert game.engine_move(state, time_limit=0.2) == 0


def test_engine_never_plays_under_a_winning_spot():
    """O non deve giocare la colonna 5: la pedina farebbe da sponda alla quaterna
    di X sulla seconda traversa (posizione verificata col motore: perde SOLO la 5)."""
    game = Connect4()
    state = game.initial_state()
    for move in [1, 2, 4, 3, 2, 1, 3, 6, 4]:
        state = game.apply(state, move)
    assert state.current == 1  # tocca a O
    losing = []
    for col in game.legal_moves(state):
        after = game.apply(state, col)
        replies = game.legal_moves(after)
        if any(game.outcome(game.apply(after, c)).winner == 0 for c in replies):
            losing.append(col)
    assert losing == [5]  # la posizione fa quel che promette
    assert game.engine_move(state, time_limit=0.2) != 5


def test_engine_returns_strong_legal_move_quickly():
    game = Connect4()
    state = game.initial_state()
    t0 = time.monotonic()
    move = game.engine_move(state, time_limit=0.5)
    assert time.monotonic() - t0 < 2.0
    assert move in game.legal_moves(state)


def test_dedicated_engine_beats_greedy():
    """Sanità di forza: il motore domina un greedy a 1 mossa (da X).

    Al meglio di tre: col budget piccolo (e la macchina sotto carico) una
    PATTA ogni tanto ci sta — una sconfitta mai, e almeno una vittoria sì.
    """
    game = Connect4()

    def greedy(state):
        best, best_score = None, None
        for m in game.legal_moves(state):
            score = game.heuristic(game.apply(state, m), state.current)
            if best_score is None or score > best_score:
                best, best_score = m, score
        return best

    results = []
    for _ in range(3):
        state = game.initial_state()
        plies = 0
        while not game.is_terminal(state) and plies < 42:
            move = game.engine_move(state, time_limit=0.15) if state.current == 0 else greedy(state)
            state = game.apply(state, move)
            plies += 1
        assert game.is_terminal(state)
        results.append(game.outcome(state).winner)
    assert 1 not in results  # mai battuto dal greedy
    assert 0 in results  # e almeno una vittoria


def test_local_player_uses_dedicated_engine():
    """Il giocatore locale della piattaforma preferisce il motore dedicato."""
    from app.opponents.local import best_move

    game = Connect4()
    state = game.initial_state()
    move, source = best_move(game, state, game.legal_moves(state), think_ms=100)
    assert source == "engine"
    assert move in game.legal_moves(state)
