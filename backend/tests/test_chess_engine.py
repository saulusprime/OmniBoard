"""Test del motore di ricerca degli scacchi (forza tattica e correttezza)."""

import time

from engine.games.chess import Chess

GAME = Chess()


def _move_id(state, time_limit=1.0, jitter=0):
    move = GAME.engine_move(state, time_limit=time_limit, jitter=jitter)
    return GAME.move_id(move)


def test_from_fen_matches_initial_state():
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    assert Chess.from_fen(fen).board == GAME.initial_state().board


def test_finds_mate_in_one():
    # Matto del corridoio: Ra1-a8#.
    state = Chess.from_fen("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1")
    assert _move_id(state) == "a1a8"


def test_captures_free_queen():
    # Donna nemica indifesa sulla stessa colonna: Qd1xd8 guadagna la donna.
    state = Chess.from_fen("3q3k/8/8/8/8/8/8/3Q3K w - - 0 1")
    assert _move_id(state) == "d1d8"


def test_avoids_losing_capture_via_quiescence():
    # Qd1xd4 "guadagna" un pedone ma è difeso da c5: cxd4 perde la donna. Da evitare.
    state = Chess.from_fen("7k/8/8/2p5/3p4/8/8/3Q3K w - - 0 1")
    assert _move_id(state, time_limit=1.0) != "d1d4"


def test_returns_legal_move_when_in_check():
    # Nero sotto scacco di torre sulla colonna e (non è matto: il re ha case di fuga).
    state = Chess.from_fen("4k3/8/8/8/8/8/8/4R2K b - - 0 1")
    legal = GAME.legal_moves(state)
    assert legal  # ci sono mosse (scacco, non matto)
    move = GAME.engine_move(state, time_limit=0.5)
    assert move in legal


def test_returns_legal_move_from_start_within_time():
    start = time.monotonic()
    move = GAME.engine_move(GAME.initial_state(), time_limit=0.4)
    elapsed = time.monotonic() - start
    assert move in GAME.legal_moves(GAME.initial_state())
    assert elapsed < 3.0  # rispetta (con margine) il budget di tempo


def test_deterministic_without_jitter():
    state = Chess.from_fen("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 1")
    first = _move_id(state, time_limit=0.6)
    second = _move_id(state, time_limit=0.6)
    assert first == second
