"""Test del motore degli scacchi (perft + casi speciali) e del libro aperture."""

from engine.games import openings
from engine.games.chess import Chess, ChessState


def _perft(game, state, depth):
    if depth == 0:
        return 1
    return sum(_perft(game, game.apply(state, m), depth - 1) for m in game.legal_moves(state))


def _play(game, state, ucis):
    for uci in ucis:
        move = next(m for m in game.legal_moves(state) if game.move_id(m) == uci)
        state = game.apply(state, move)
    return state


def test_perft_initial_position():
    game = Chess()
    state = game.initial_state()
    assert len(game.legal_moves(state)) == 20
    assert _perft(game, state, 2) == 400
    assert _perft(game, state, 3) == 8902


def test_fools_mate_is_checkmate():
    game = Chess()
    state = _play(game, game.initial_state(), ["f2f3", "e7e5", "g2g4", "d8h4"])
    assert game.is_terminal(state)
    assert game.outcome(state).winner == 1  # vince il Nero


def test_stalemate_is_draw():
    game = Chess()
    # Re nero in a8, Donna bianca in b6, Re bianco in c6: Nero in stallo, muove il Nero.
    board = [None] * 64
    board[0] = "k"  # a8
    board[2 * 8 + 1] = "Q"  # b6
    board[2 * 8 + 2] = "K"  # c6
    state = ChessState(
        board=tuple(board), current=1, castling=(False, False, False, False), ep=None, halfmove=0
    )
    assert game.legal_moves(state) == []
    assert game.is_terminal(state)
    assert game.outcome(state).winner is None  # stallo = patta


def test_promotion_moves_present():
    game = Chess()
    board = [None] * 64
    board[1 * 8 + 0] = "P"  # a7
    board[7 * 8 + 4] = "K"
    board[0 * 8 + 4] = "k"
    state = ChessState(
        board=tuple(board), current=0, castling=(False, False, False, False), ep=None, halfmove=0
    )
    ids = {game.move_id(m) for m in game.legal_moves(state)}
    assert {"a7a8q", "a7a8r", "a7a8b", "a7a8n"} <= ids


def test_opening_detection():
    assert openings.detect_opening(["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"]) == "Partita Italiana"
    assert openings.detect_opening(["e2e4", "c7c5"]) == "Difesa Siciliana"
    assert openings.detect_opening(["e2e4", "e7e5", "g1f3", "b8c6", "d2d4"]) == "Partita Scozzese"
    assert openings.detect_opening([]) is None


def test_opening_book_move_is_legal():
    game = Chess()
    move = game.opening_move(game.initial_state(), [])
    assert move in game.legal_moves(game.initial_state())
