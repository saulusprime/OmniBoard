"""Test dei potenziamenti di ricerca: SEE, e sanità del motore potenziato."""

from engine import get_game
from engine.chess.engine import _see, best_move


def _board(pieces: dict[int, str]) -> tuple:
    board = [None] * 64
    for sq, piece in pieces.items():
        board[sq] = piece
    return tuple(board)


def test_see_judges_exchanges():
    # DxP difeso da pedone: 100 − 900 = scambio perdente.
    # d5=27, pedone nero difeso da e6=20; donna bianca d1=59.
    board = _board({27: "p", 20: "p", 59: "Q", 0: "k", 63: "K"})
    assert _see(board, (59, 27, None)) == -800
    # TxD indifesa: guadagno pieno.
    board = _board({0: "q", 56: "R", 4: "k", 60: "K"})
    assert _see(board, (56, 0, None)) == 900
    # CxP difeso da torre: perdente (100 − 320 ricatturato)…
    board = _board({27: "p", 3: "r", 44: "N", 0: "k", 63: "K"})
    assert _see(board, (44, 27, None)) == -220
    # …ma con la donna in RAGGI X dietro la colonna, lo scambio torna a +100:
    # CxP, TxC, DxT — e il nero farebbe meglio a fermarsi comunque.
    board = _board({27: "p", 3: "r", 44: "N", 59: "Q", 0: "k", 63: "K"})
    assert _see(board, (44, 27, None)) == 100


def test_engine_still_finds_mate():
    """I pruning (SEE/futility/aspiration/PVS) non devono mai mangiarsi un matto."""
    game = get_game("chess")
    # Matto del corridoio in 1: Te1-e8#.
    state = game.from_fen("6k1/5ppp/8/8/8/8/8/4R2K w - - 0 1")
    move = best_move(game, state, time_limit=2.0, jitter=0)
    assert game.move_id(move) == "e1e8"


def test_engine_does_not_hang_pieces():
    """La quiescence con SEE continua a vedere gli scambi: niente donna in presa."""
    game = get_game("chess")
    # Donna bianca su e4, ATTACCATA dal pedone d5 (che cattura in diagonale) e
    # con d5 difesa dalla donna nera in d8: né restare né prendere il pedone.
    state = game.from_fen("rnbqkbnr/ppp1pppp/8/3p4/4Q3/8/PPPP1PPP/RNB1KBNR w KQkq - 0 1")
    move = best_move(game, state, time_limit=1.5, jitter=0)
    frm, to, _ = move
    assert frm == 36  # e4: muove proprio la donna minacciata
    assert to != 27  # e NON cattura d5 (difeso: lo scambio perde la donna)
