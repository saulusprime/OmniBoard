"""Test del libro Polyglot: vettori UFFICIALI della specifica + probing su .bin."""

import struct

from engine import get_game
from engine.chess import polyglot
from engine.chess.game import Chess

# Vettori di test della specifica del formato (hgm.nubati.net/book_format.html):
# sequenza di mosse dalla posizione iniziale → chiave Zobrist attesa.
SPEC_VECTORS = [
    ([], 0x463B96181691FC9C),
    (["e2e4"], 0x823C9B50FD114196),
    (["e2e4", "d7d5"], 0x0756B94461C50FB0),
    (["e2e4", "d7d5", "e4e5"], 0x662FAFB965DB29D4),
    (["e2e4", "d7d5", "e4e5", "f7f5"], 0x22A48B5A8E47FF78),
    (["e2e4", "d7d5", "e4e5", "f7f5", "e1e2"], 0x652A607CA3F242C1),
    (["e2e4", "d7d5", "e4e5", "f7f5", "e1e2", "e8f7"], 0x00FDD303C946BDD9),
    (["a2a4", "b7b5", "h2h4", "b5b4", "c2c4"], 0x3C8123EA7B067637),
    (["a2a4", "b7b5", "h2h4", "b5b4", "c2c4", "b4c3", "a1a3"], 0x5C3F9B829B279560),
]


def _play(game, ucis):
    state = game.initial_state()
    for uci in ucis:
        move = next(m for m in game.legal_moves(state) if game.move_id(m) == uci)
        state = game.apply(state, move)
    return state


def test_zobrist_matches_official_vectors():
    """La tabella RANDOM64 e l'hashing riproducono ESATTAMENTE la specifica
    (arrocchi, en passant condizionale, tratto compresi)."""
    game = get_game("chess")
    for ucis, expected in SPEC_VECTORS:
        assert polyglot.zobrist_key(_play(game, ucis)) == expected, ucis


def _entry(key, uci, weight=100):
    to_col, to_row = ord(uci[2]) - 97, int(uci[3]) - 1
    fr_col, fr_row = ord(uci[0]) - 97, int(uci[1]) - 1
    raw = to_col | (to_row << 3) | (fr_col << 6) | (fr_row << 9)
    return struct.pack(">QHHI", key, raw, weight, 0)


def test_probe_and_opening_move_from_bin(tmp_path, monkeypatch):
    game = get_game("chess")
    start_key = 0x463B96181691FC9C
    # Libro con due voci per la posizione iniziale (ordinato per chiave) e una
    # voce con l'arrocco in stile Polyglot (re cattura torre) da una posizione test.
    # Posizione FUORI dal libro incorporato (che ha priorità sul Polyglot):
    # arrocco corto bianco legale dopo sviluppi con mosse d'ala rare.
    castle_state = _play(game, ["e2e4", "e7e5", "g1f3", "g8f6", "f1c4", "a7a6", "a2a4", "a6a5"])
    castle_key = polyglot.zobrist_key(castle_state)
    entries = sorted(
        [
            _entry(start_key, "e2e4", 90),
            _entry(start_key, "d2d4", 10),
            _entry(castle_key, "e1h1", 50),  # arrocco corto in notazione Polyglot
        ]
    )
    book = tmp_path / "libro.bin"
    book.write_bytes(b"".join(entries) + b"\x00")  # byte spurio in coda: va tollerato
    monkeypatch.setenv("CHESS_POLYGLOT_BOOK", str(book))
    monkeypatch.delenv("CHESS_BOOK_FILE", raising=False)
    Chess.reset_book_cache()
    polyglot.reset_cache()

    found = dict(polyglot.probe(game.initial_state()))
    assert found == {"e2e4": 90, "d2d4": 10}

    # L'arrocco «e1h1» diventa la nostra mossa e1g1, legale e giocabile.
    assert polyglot.probe(castle_state) == [("e1g1", 50)]
    move = game.opening_move(castle_state, [])
    assert game.move_id(move) == "e1g1"

    # Posizione fuori libro → nessuna mossa (e nessun errore).
    after = _play(game, ["b1c3"])
    assert polyglot.probe(after) == []
    Chess.reset_book_cache()


def test_weighted_choice_respects_weights():
    picks = {polyglot.weighted_choice([("a", 0), ("b", 0)]) for _ in range(20)}
    assert picks <= {"a", "b"}  # pesi nulli: uniforme, mai errori
    heavy = [polyglot.weighted_choice([("a", 1), ("b", 999)]) for _ in range(50)]
    assert heavy.count("b") > 40  # il peso comanda
