"""Test del Backgammon: nodi del caso, regole di movimento, colpi, barra, uscita.

I dadi vengono applicati con ``apply_chance`` e tiri espliciti: i test sono
deterministici (l'estrazione casuale è responsabilità del backend, non del motore).
"""

from engine import get_game, is_playable
from engine.backgammon import Backgammon, BackgammonState

GAME = Backgammon()


def _state(points=None, bar=(0, 0), off=(0, 0), current=0, dice=None):
    """Costruisce uno stato di comodo: ``points`` è un dict {punta: valore con segno}."""
    board = [0] * 24
    for point, value in (points or {}).items():
        board[point] = value
    return BackgammonState(points=tuple(board), bar=bar, off=off, current=current, dice=dice)


def test_registered_and_playable():
    assert is_playable("backgammon")
    assert get_game("backgammon").is_stochastic is True


def test_initial_state_is_chance_node_with_15_checkers_each():
    state = GAME.initial_state()
    assert sum(v for v in state.points if v > 0) == 15  # pedine di X
    assert sum(-v for v in state.points if v < 0) == 15  # pedine di O
    assert GAME.is_chance_node(state)  # i primi dadi sono da tirare
    assert GAME.legal_moves(state) == []  # nessuna mossa finché non si tira


def test_chance_outcomes_cover_all_rolls():
    outcomes = GAME.chance_outcomes(GAME.initial_state())
    assert len(outcomes) == 21  # 15 coppie distinte + 6 doppi
    assert abs(sum(p for _e, p in outcomes) - 1.0) < 1e-9
    probs = dict(outcomes)
    assert probs[(3, 3)] == 1 / 36  # doppio
    assert probs[(6, 5)] == 2 / 36  # coppia non doppia (esce in due modi)


def test_apply_chance_sets_dice_and_doubles_give_four_moves():
    state = GAME.initial_state()
    rolled = GAME.apply_chance(state, (6, 5))
    assert rolled.dice == (6, 5)
    doubled = GAME.apply_chance(state, (4, 4))
    assert doubled.dice == (4, 4, 4, 4)  # un doppio vale quattro mosse


def test_legal_moves_respect_blocked_points():
    # Dalla posizione iniziale col 5: da 23 si andrebbe su 18 (5 pedine O: bloccata),
    # da 12 si va su 7 (proprie pedine: lecita).
    state = GAME.apply_chance(GAME.initial_state(), (6, 5))
    ids = {GAME.move_id(m) for m in GAME.legal_moves(state)}
    assert "12:5" in ids
    assert "23:5" not in ids  # punta 18 bloccata da ≥2 pedine avversarie
    assert "23:6" in ids  # punta 17 libera


def test_hit_sends_single_opponent_checker_to_bar():
    # X su 10 muove di 3 su 7, dove O ha UNA sola pedina: colpo → O sulla barra.
    state = _state(points={10: 1, 7: -1, 0: -2}, current=0, dice=(3,))
    move = next(m for m in GAME.legal_moves(state) if GAME.move_id(m) == "10:3")
    assert GAME.describe_move(state, move).endswith("*")  # notazione del colpo
    after = GAME.apply(state, move)
    assert after.points[7] == 1  # ora c'è la pedina di X
    assert after.bar == (0, 1)  # la pedina di O è sulla barra


def test_bar_entry_is_mandatory():
    # X ha una pedina sulla barra: le uniche mosse sono i rientri (24 - dado).
    state = _state(points={10: 2, 20: -2}, bar=(1, 0), current=0, dice=(6, 3))
    ids = {GAME.move_id(m) for m in GAME.legal_moves(state)}
    assert ids == {"bar:6", "bar:3"}  # 24-6=18 e 24-3=21, entrambe libere
    after = GAME.apply(state, next(iter(GAME.legal_moves(state))))
    assert after.bar[0] == 0  # rientrata


def test_bear_off_requires_all_home_and_respects_overshoot():
    # Tutte le pedine di X in casa (punte 0..5): può uscire.
    home = _state(points={5: 2, 3: 1, 0: -2}, off=(12, 0), current=0, dice=(6, 4))
    ids = {GAME.move_id(m) for m in GAME.legal_moves(home)}
    assert "5:6" in ids  # dado 6 > pip 6? pip di 5 è 6 → esatto: esce
    # dado 4: da 5 andrebbe su 1 (mossa interna), da 3 (pip 4) esce esatto
    assert "3:4" in ids
    # Con una pedina ancora fuori casa l'uscita è vietata.
    not_home = _state(points={5: 1, 10: 1, 0: -2}, off=(13, 0), current=0, dice=(6,))
    assert all(GAME.move_id(m) != "5:6" for m in GAME.legal_moves(not_home))
    # Dado ESATTO: lecito anche se punte più lontane sono occupate (pip di 3 è 4).
    two = _state(points={5: 1, 3: 1, 0: -2}, off=(13, 0), current=0, dice=(4,))
    assert "3:4" in {GAME.move_id(m) for m in GAME.legal_moves(two)}
    # Scarto (dado MAGGIORE del pip): vietato finché la punta più lontana è occupata…
    over = _state(points={5: 1, 3: 1, 0: -2}, off=(13, 0), current=0, dice=(5,))
    assert "3:5" not in {GAME.move_id(m) for m in GAME.legal_moves(over)}
    # …e lecito quando la punta è la più lontana rimasta.
    alone = _state(points={3: 1, 0: -2}, off=(14, 0), current=0, dice=(5,))
    assert "3:5" in {GAME.move_id(m) for m in GAME.legal_moves(alone)}


def test_turn_passes_when_roll_unplayable():
    # X sulla barra con TUTTI i punti di rientro (18..23) bloccati: qualunque tiro
    # è ingiocabile → il turno passa a O (nuovo nodo del caso).
    blocked = {p: -2 for p in range(18, 24)}
    blocked[0] = 2  # una pedina X sul tavoliere (oltre a quella sulla barra)
    state = _state(points=blocked, bar=(1, 0), current=0, dice=None)
    rolled = GAME.apply_chance(state, (6, 1))
    assert rolled.current == 1  # il turno è passato a O
    assert rolled.dice is None  # che dovrà tirare a sua volta
    assert GAME.is_chance_node(rolled)


def test_win_by_bearing_off_all_checkers():
    state = _state(points={0: 1, 20: -2}, off=(14, 0), current=0, dice=(1, 2))
    move = next(m for m in GAME.legal_moves(state) if GAME.move_id(m) == "0:1")
    after = GAME.apply(state, move)
    assert after.off[0] == 15
    assert GAME.is_terminal(after)
    assert GAME.outcome(after).winner == 0


def test_serialize_round_trip_and_views():
    state = GAME.apply_chance(GAME.initial_state(), (6, 5))
    again = GAME.deserialize_state(GAME.serialize_state(state))
    assert again == state
    cells = GAME.view_board(state)
    assert len(cells) == 28  # griglia 2×14 (punte + barre + uscite)
    assert cells[GAME._view_index(23)] == "2○"  # le due pedine X sulla 23
    assert cells[GAME._view_index(11)] == "5●"  # le cinque pedine O sulla 11
    # L'euristica della posizione iniziale è simmetrica: valore nullo per entrambi.
    assert GAME.heuristic(state, 0) == 0
    assert GAME.heuristic(state, 1) == 0
    assert "Dadi da giocare" in GAME.view_status(state)
