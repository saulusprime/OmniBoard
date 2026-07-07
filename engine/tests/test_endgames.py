"""Test dei finali: mop-up (matto portato a casa) e riconoscimento KPK."""

from engine import get_game
from engine.chess.engine import best_move, evaluate


def _eval_fen(fen):
    game = get_game("chess")
    state = game.from_fen(fen)
    return game, state, evaluate(game, state)


def test_kpk_rule_of_the_square():
    # Pedone b5, re nero in a2: FUORI dal quadrato → promozione imprendibile.
    _, _, score = _eval_fen("8/8/8/1P6/8/8/k7/4K3 w - - 0 1")
    assert score > 500
    # Re difensore piantato davanti al pedone: tendente alla patta.
    _, _, score = _eval_fen("8/8/8/8/4k3/8/4P3/4K3 w - - 0 1")
    assert abs(score) < 120
    # Pedone di torre col re difensore nell'angolo di promozione: patta da manuale.
    _, _, score = _eval_fen("k7/8/8/P7/8/8/8/4K3 w - - 0 1")
    assert abs(score) < 120


def test_mopup_pushes_the_king_to_the_edge():
    # A parità di materiale (KQ vs K), il re nero ALL'ANGOLO con i re vicini vale
    # più del re nero al centro con i re lontani: è il piano del matto.
    _, _, near_corner = _eval_fen("7k/8/5K2/8/8/8/Q7/8 w - - 0 1")
    _, _, centered = _eval_fen("8/8/8/3k4/8/8/Q7/6K1 w - - 0 1")
    assert near_corner > centered


def test_engine_delivers_mate_in_kq_endgame():
    """Prova FUNZIONALE: da KQ vs K il motore deve MATTARE, non rimescolare.

    Il piano oltre l'orizzonte lo dà il gradiente del mop-up (re avversario al
    bordo + re vicini): a 0,5 s/mossa il matto arriva in ~7 mosse.
    """
    game = get_game("chess")
    state = game.from_fen("8/8/8/3k4/8/8/4Q3/4K3 w - - 0 1")
    plies = 0
    seen: list[str] = []
    while not game.is_terminal(state) and plies < 70:
        move = best_move(game, state, history=None, time_limit=0.5, jitter=0)
        seen.append(game.move_id(move))
        state = game.apply(state, move)
        plies += 1
    assert game.is_terminal(state), f"niente matto entro 35 mosse: {' '.join(seen)}"
    assert game.outcome(state).winner == 0  # vince il bianco (matto, non stallo)
