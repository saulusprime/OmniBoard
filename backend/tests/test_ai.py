"""Test della selezione mossa dell'IA remota (parsing risposta), senza rete."""

from app import ai

from engine import get_game


def test_match_move_chess_by_uci():
    game = get_game("chess")
    state = game.initial_state()
    legal = game.legal_moves(state)
    move = ai._match_move(game, legal, "Penso che la mossa migliore sia e2e4, decisa.")
    assert game.move_id(move) == "e2e4"


def test_match_move_none_when_absent():
    game = get_game("chess")
    state = game.initial_state()
    legal = game.legal_moves(state)
    assert ai._match_move(game, legal, "non ne ho idea") is None


def test_match_move_tictactoe_index():
    game = get_game("tictactoe")
    state = game.initial_state()
    legal = game.legal_moves(state)
    move = ai._match_move(game, legal, "Gioco nella casella 4 (centro).")
    assert game.move_id(move) == "4"


def test_match_move_draughts_path():
    game = get_game("checkers")
    state = game.initial_state()
    legal = game.legal_moves(state)
    target = game.move_id(legal[0])  # es. "40-33"
    move = ai._match_move(game, legal, f"La mia mossa: {target}")
    assert game.move_id(move) == target
