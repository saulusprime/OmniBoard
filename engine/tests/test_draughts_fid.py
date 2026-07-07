"""Dama italiana: priorità FID sulle catture, ripetizione, motore dedicato."""

import time

from engine import get_game
from engine.draughts.game import Draughts
from engine.draughts.state import DraughtsState

W, WK, B, BK = (0, False), (0, True), (1, False), (1, True)


def _board(pieces: dict[int, tuple]) -> tuple:
    board = [None] * 64
    for sq, piece in pieces.items():
        board[sq] = piece
    return tuple(board)


def _sq(r: int, c: int) -> int:
    return r * 8 + c


def test_equal_count_must_capture_with_king():
    """FID: a parità di pezzi presi, è obbligatorio prendere con la DAMA."""
    game = get_game("checkers")
    # La pedina in (5,2) può prendere la pedina in (4,3); la DAMA in (5,6) può
    # prendere quella in (4,5). Una presa a testa: si DEVE usare la dama.
    state = DraughtsState(
        board=_board({_sq(5, 2): W, _sq(4, 3): B, _sq(5, 6): WK, _sq(4, 5): B}),
        current=0,
    )
    assert game.legal_moves(state) == [(_sq(5, 6), _sq(3, 4))]


def test_equal_count_prefers_more_kings_captured():
    """FID: a parità di pezzi, si prende il maggior numero di DAME."""
    game = get_game("checkers")
    # La dama bianca in (7,4) ha due prese doppie: a sinistra pedina+pedina,
    # a destra pedina+DAMA. Vale solo la linea che cattura la dama.
    state = DraughtsState(
        board=_board(
            {
                _sq(7, 4): WK,
                _sq(6, 3): B,  # linea sinistra: due pedine
                _sq(4, 1): B,
                _sq(6, 5): B,  # linea destra: pedina + dama
                _sq(4, 5): BK,
            }
        ),
        current=0,
    )
    assert game.legal_moves(state) == [(_sq(7, 4), _sq(5, 6), _sq(3, 4))]


def test_equal_kings_prefers_meeting_king_first():
    """FID: a parità di dame catturate, vale la linea che incontra PRIMA la dama."""
    game = get_game("checkers")
    # Due prese doppie da (7,4), una dama catturata per parte: a sinistra la
    # dama è il PRIMO pezzo preso, a destra il SECONDO. Vale solo la sinistra.
    state = DraughtsState(
        board=_board(
            {
                _sq(7, 4): WK,
                _sq(6, 3): BK,  # sinistra: DAMA poi pedina
                _sq(4, 1): B,
                _sq(6, 5): B,  # destra: pedina poi DAMA
                _sq(4, 5): BK,
            }
        ),
        current=0,
    )
    moves = game.legal_moves(state)
    assert moves == [(_sq(7, 4), _sq(5, 2), _sq(3, 0))]


def test_man_still_cannot_capture_king():
    game = get_game("checkers")
    state = DraughtsState(board=_board({_sq(5, 2): W, _sq(4, 3): BK}), current=0)
    moves = game.legal_moves(state)
    assert all(abs(m[1] // 8 - m[0] // 8) == 1 for m in moves)  # solo passi semplici


def test_repetition_draw_with_kings():
    """Terza occorrenza della posizione → patta (le pedine sole non ripetono mai)."""
    game = Draughts()  # istanza dedicata: si ridefinisce la posizione di partenza
    start = DraughtsState(board=_board({_sq(7, 0): WK, _sq(0, 7): BK}), current=0)
    game.initial_state = lambda: start  # solo per il test (mai il globale di get_game)
    shuffle = ["56-49", "7-14", "49-56", "14-7"]
    assert game.is_repetition_draw(shuffle) is False  # posizione di nuovo qui: 2 volte
    assert game.is_repetition_draw(shuffle * 2) is True  # terza occorrenza
    # Storia non ricostruibile: mai una dichiarazione (prudenza, come gli scacchi).
    assert get_game("checkers").is_repetition_draw(["56-49", "7-14"] * 4) is False


def test_engine_returns_strong_legal_move_quickly():
    game = get_game("checkers")
    state = game.initial_state()
    t0 = time.monotonic()
    move = game.engine_move(state, time_limit=0.5)
    assert time.monotonic() - t0 < 2.0
    assert move in game.legal_moves(state)


def test_engine_avoids_the_shot():
    """Il motore non regala una presa: (4,3)→(3,4) offrirebbe il pezzo al Nero."""
    game = get_game("checkers")
    state = DraughtsState(
        board=_board(
            {
                _sq(4, 3): W,
                _sq(6, 1): W,
                _sq(7, 2): W,
                _sq(2, 5): B,
                _sq(1, 6): B,
                _sq(0, 7): BK,
            }
        ),
        current=0,
    )
    move = game.engine_move(state, time_limit=0.4)
    assert move in game.legal_moves(state)
    after = game.apply(state, move)
    # Dopo la mossa del motore il Nero non ha nessuna presa disponibile.
    assert all(abs(m[1] // 8 - m[0] // 8) == 1 for m in game.legal_moves(after))


def test_dedicated_engine_beats_greedy():
    """Sanità di forza: il motore iterativo domina un giocatore greedy a 1 mossa."""
    game = get_game("checkers")

    def greedy(state):
        best, best_score = None, None
        for m in game.legal_moves(state):
            nxt = game.apply(state, m)
            score = -game.heuristic(nxt, nxt.current)
            if best_score is None or score > best_score:
                best, best_score = m, score
        return best

    state = game.initial_state()
    plies = 0
    while not game.is_terminal(state) and plies < 120:
        move = game.engine_move(state, time_limit=0.1) if state.current == 0 else greedy(state)
        state = game.apply(state, move)
        plies += 1
    if game.is_terminal(state):
        assert game.outcome(state).winner == 0  # vince il motore dedicato
    else:
        assert game.heuristic(state, 0) > 6  # almeno due pedine di vantaggio netto
