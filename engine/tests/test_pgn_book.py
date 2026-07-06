"""Test dell'import PGN nel libro: parser SAN e caricamento via CHESS_BOOK_FILE."""

from engine import get_game
from engine.chess import pgn
from engine.chess.game import Chess

PGN = """[Event "Prova"]
[White "Rossi"]
[Black "Bianchi"]
[ECO "C50"]
[Opening "Partita Italiana"]

1. e4 e5 2. Nf3 {sviluppo} Nc6 3. Bc4 (3. Bb5 a6) Bc5 $1 4. O-O 1-0

[Event "Prova 2"]
[White "Verdi"]
[Black "Neri"]

1. d4 d5 2. c4 dxc4 1/2-1/2
"""


def test_san_translation_and_pgn_lines():
    game = get_game("chess")
    lines = pgn.parse_pgn(game, PGN)
    assert len(lines) == 2
    name, moves = lines[0]
    # Tag ECO+Opening nel nome; SAN → UCI con cattura, arrocco e commenti/varianti puliti.
    assert name == "C50 Partita Italiana"
    assert moves == ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "e1g1"]
    name2, moves2 = lines[1]
    assert name2 == "Verdi–Neri"
    assert moves2 == ["d2d4", "d7d5", "c2c4", "d5c4"]  # dxc4 = cattura di pedone


def test_san_disambiguation_and_promotion():
    game = get_game("chess")
    state = game.initial_state()
    # Disambiguazione per colonna: due cavalli potrebbero andare in d2? Costruiamo
    # una posizione semplice rigiocando: 1.Nf3 a6 2.Nc3 → "Nd4" sarebbe ambigua? No:
    # verifichiamo il caso reale Nbd2 dopo 1.Nf3 d5 2.d3.
    for uci in ("g1f3", "d7d5", "d2d3", "a7a6"):
        move = next(m for m in game.legal_moves(state) if game.move_id(m) == uci)
        state = game.apply(state, move)
    assert pgn.san_to_uci(game, state, "Nbd2") == "b1d2"
    assert pgn.san_to_uci(game, state, "Nfd2") == "f3d2"
    assert pgn.san_to_uci(game, state, "Nd2") is None  # ambigua: nessuna scelta
    assert pgn.san_to_uci(game, state, "Zx9") is None  # spazzatura


def test_book_file_accepts_pgn(tmp_path, monkeypatch):
    book = tmp_path / "repertorio.pgn"
    book.write_text(PGN)
    monkeypatch.setenv("CHESS_BOOK_FILE", str(book))
    Chess.reset_book_cache()
    game = get_game("chess")
    # Il libro segue la linea PGN preferita come bersaglio (riusa il filtro prefer).
    move = game.opening_move(game.initial_state(), [], prefer=["Partita Italiana"])
    assert game.move_id(move) == "e2e4"
    Chess.reset_book_cache()
