"""Test del libro di aperture ampliato: validità delle linee, nomi, trasposizioni,
file esterno."""

from engine.chess import Chess, openings

GAME = Chess()


def _play(state, uci):
    move = next((m for m in GAME.legal_moves(state) if GAME.move_id(m) == uci), None)
    assert move is not None, f"mossa non legale: {uci}"
    return GAME.apply(state, move)


def test_all_builtin_lines_are_fully_legal():
    """Ogni linea del libro integrato deve essere interamente rigiocabile."""
    for name, line in openings.OPENINGS:
        state = GAME.initial_state()
        for uci in line:
            move = next((m for m in GAME.legal_moves(state) if GAME.move_id(m) == uci), None)
            assert move is not None, f"mossa non valida {uci!r} nella linea «{name}»"
            state = GAME.apply(state, move)


def test_book_breadth():
    assert len(openings.OPENINGS) >= 60  # libro "ampio": famiglie principali + varianti


def test_detection_prefers_specific_variation():
    najdorf = ["e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6", "b1c3", "a7a6"]
    assert "Najdorf" in openings.detect_opening(najdorf)
    # A profondità bassa vince il nome generico della famiglia.
    assert openings.detect_opening(["e2e4", "c7c5"]) == "Difesa Siciliana"
    assert openings.detect_opening(["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"]) == "Partita Italiana"


def test_book_move_by_transposition():
    # Posizione del Colle (1.d4 d5 2.Nf3 Nf6) raggiunta con l'ordine 1.Nf3 d5 2.d4 Nf6:
    # nessuna linea del libro ha questo ordine di mosse, ma la POSIZIONE è nel libro.
    state = GAME.initial_state()
    for uci in ["g1f3", "d7d5", "d2d4", "g8f6"]:
        state = _play(state, uci)
    move = GAME.opening_move(state, ["g1f3", "d7d5", "d2d4", "g8f6"])
    assert move is not None
    assert GAME.move_id(move) == "e2e3"  # continuazione del Sistema Colle


def test_external_book_file_extends_and_truncates(tmp_path, monkeypatch):
    book = tmp_path / "book.txt"
    book.write_text(
        "# commento ignorato\nGambetto di prova: a2a3 h7h6 b2b4\nLinea rotta: a2a4 z9z9 h7h6\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CHESS_BOOK_FILE", str(book))
    Chess.reset_book_cache()
    try:
        # La linea utente valida estende il libro.
        after = _play(GAME.initial_state(), "a2a3")
        move = GAME.opening_move(after, ["a2a3"])
        assert move is not None and GAME.move_id(move) == "h7h6"
        # La linea con una mossa non valida viene troncata al prefisso valido.
        after_bad = _play(GAME.initial_state(), "a2a4")
        assert GAME.opening_move(after_bad, ["a2a4"]) is None
    finally:
        Chess.reset_book_cache()  # l'indice si ricostruirà senza il file (env rimosso)
