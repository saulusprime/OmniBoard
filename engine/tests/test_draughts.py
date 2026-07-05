"""Test del gioco Dama italiana."""

from engine.draughts import SIZE, Draughts, DraughtsState


def idx(r, c):
    return r * SIZE + c


def test_initial_state():
    game = Draughts()
    state = game.initial_state()
    assert sum(1 for c in state.board if c is not None) == 24
    assert game.current_player(state) == 0
    assert len(game.legal_moves(state)) == 7  # apertura del Bianco


def test_capture_is_mandatory():
    game = Draughts()
    board = [None] * 64
    board[idx(4, 3)] = (0, False)
    board[idx(3, 2)] = (1, False)
    state = DraughtsState(board=tuple(board), current=0)
    moves = game.legal_moves(state)
    assert moves == [(idx(4, 3), idx(2, 1))]  # unica mossa: la cattura


def test_man_cannot_capture_king():
    game = Draughts()
    board = [None] * 64
    board[idx(4, 3)] = (0, False)
    board[idx(3, 2)] = (1, True)  # dama nera adiacente
    state = DraughtsState(board=tuple(board), current=0)
    moves = game.legal_moves(state)
    assert moves  # ci sono mosse
    assert all(len(m) == 2 for m in moves)  # solo mosse semplici, nessuna cattura


def test_maximum_capture_rule():
    game = Draughts()
    board = [None] * 64
    board[idx(5, 2)] = (0, False)
    board[idx(4, 1)] = (1, False)
    board[idx(2, 1)] = (1, False)
    state = DraughtsState(board=tuple(board), current=0)
    moves = game.legal_moves(state)
    assert all(len(m) - 1 == 2 for m in moves)  # obbligo della doppia cattura
    assert (idx(5, 2), idx(3, 0), idx(1, 2)) in moves


def test_promotion_to_king():
    game = Draughts()
    board = [None] * 64
    board[idx(1, 2)] = (0, False)
    state = DraughtsState(board=tuple(board), current=0)
    move = game.legal_moves(state)[0]
    promoted = game.apply(state, move)
    assert promoted.board[move[-1]] == (0, True)


def test_serialize_roundtrip():
    game = Draughts()
    state = game.initial_state()
    assert game.deserialize_state(game.serialize_state(state)) == state
