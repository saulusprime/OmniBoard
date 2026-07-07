"""Test delle aperture-bersaglio: il libro preferisce le linee deboli dell'avversario.

Il libro viene controllato con un file utente minimo (due linee dalla posizione
iniziale): con il bersaglio la scelta diventa deterministica, senza resta libera.
"""

from types import SimpleNamespace

from app import gameplay, opponents

from engine import get_game
from engine.chess.game import Chess


def _mini_book(tmp_path, monkeypatch):
    book = tmp_path / "book.txt"
    book.write_text("Linea Alfa: e2e4 e7e5\nLinea Beta: d2d4 d7d5\n")
    monkeypatch.setenv("CHESS_BOOK_FILE", str(book))
    Chess.reset_book_cache()


def test_book_prefers_target_opening(tmp_path, monkeypatch):
    _mini_book(tmp_path, monkeypatch)
    game = get_game("chess")
    state = game.initial_state()
    # Con il bersaglio «Linea Beta» la mossa è SEMPRE d2d4 (mai casuale).
    for _ in range(10):
        move = game.opening_move(state, [], prefer=["Linea Beta"])
        assert game.move_id(move) == "d2d4"
    # Il confronto per sottostringa aggancia anche le varianti nominate.
    move = game.opening_move(state, [], prefer=["linea alfa — variante di prova"])
    assert game.move_id(move) == "e2e4"
    Chess.reset_book_cache()


def test_unknown_target_falls_back_to_whole_book(tmp_path, monkeypatch):
    _mini_book(tmp_path, monkeypatch)
    game = get_game("chess")
    state = game.initial_state()
    # Il file utente SI SOMMA al libro incorporato: senza aggancio la scelta torna
    # libera su tutto il libro (più mosse possibili, non solo la linea bersaglio).
    seen = {game.move_id(game.opening_move(state, [], prefer=["Inesistente"])) for _ in range(40)}
    assert len(seen) >= 2
    Chess.reset_book_cache()


def test_dispatcher_passes_targets_from_style(tmp_path, monkeypatch):
    _mini_book(tmp_path, monkeypatch)
    game = get_game("chess")
    state = game.initial_state()
    move, source = opponents.choose_move(
        game,
        state,
        history=[],
        kind="ai",
        style={"aggression": 0, "contempt": 0, "target_openings": ["Linea Beta"]},
    )
    assert source == "book" and game.move_id(move) == "d2d4"
    Chess.reset_book_cache()


def test_opponent_style_carries_weakest_openings(monkeypatch):
    """Il profilo dell'avversario umano alimenta lo stile con le aperture-bersaglio."""
    from app import profile_cache

    # opponent_style ora passa dalla cache del profilo: si finge quel livello.
    monkeypatch.setattr(
        profile_cache,
        "get",
        lambda db, uid: {
            "style": {"aggression": 0.2, "contempt": 10},
            "weakest_openings": ["Difesa Siciliana", "Gambetto di Donna"],
        },
    )
    game = get_game("chess")
    session = SimpleNamespace(x_is_ai=True, o_is_ai=False, o_user_id=7, x_user_id=None)
    style = gameplay.opponent_style(None, game, session)
    assert style["target_openings"] == ["Difesa Siciliana", "Gambetto di Donna"]
    assert style["aggression"] == 0.2  # lo stile esistente resta intatto
