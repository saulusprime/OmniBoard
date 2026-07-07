"""Test dello scrittore SAN (uci_to_san / san_line): l'inverso del parser PGN."""

from engine import get_game
from engine.chess.pgn import san_line, san_to_uci, uci_to_san

FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]


def test_fools_mate_line():
    game = get_game("chess")
    assert san_line(game, FOOLS_MATE) == ["f3", "e5", "g4", "Qh4#"]


def test_capture_check_and_castle():
    game = get_game("chess")
    # Arrocco corto da FEN con solo re e torre.
    state = game.from_fen("4k3/8/8/8/8/8/8/4K2R w K - 0 1")
    assert uci_to_san(game, state, "e1g1") == "O-O"
    # Cattura di pedone en passant: il pedone cambia colonna su casa vuota.
    state = game.from_fen("4k3/8/8/3Pp3/8/8/8/4K3 w - e6 0 1")
    assert uci_to_san(game, state, "d5e6") == "dxe6"
    # Promozione con cattura e scacco lungo l'ottava traversa.
    state = game.from_fen("1n2k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    assert uci_to_san(game, state, "a7b8q") == "axb8=Q+"


def test_disambiguation_file_and_rank():
    game = get_game("chess")
    # Due cavalli sulla stessa traversa: basta la colonna di partenza.
    state = game.from_fen("4k3/8/8/8/8/8/8/1N2KN2 w - - 0 1")
    assert uci_to_san(game, state, "b1d2") == "Nbd2"
    assert uci_to_san(game, state, "f1d2") == "Nfd2"
    # Due torri sulla stessa colonna: serve la traversa.
    state = game.from_fen("4k3/8/8/R7/8/8/8/R3K3 w - - 0 1")
    assert uci_to_san(game, state, "a1a3") == "R1a3"
    assert uci_to_san(game, state, "a5a3") == "R5a3"
    # Mossa illegale o non ricostruibile: None, mai una SAN inventata.
    assert uci_to_san(game, state, "a1h8") is None


def test_san_line_roundtrips_with_parser():
    """Ogni SAN emessa deve ritradursi nella STESSA mossa UCI dal parser."""
    game = get_game("chess")
    history = ["e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6"]
    sans = san_line(game, history)
    assert len(sans) == len(history)
    state = game.initial_state()
    for uci, san in zip(history, sans):
        assert san_to_uci(game, state, san) == uci
        state = game.apply(
            state, next(m for m in game.legal_moves(state) if game.move_id(m) == uci)
        )


def test_san_line_from_fen_stops_on_bad_history():
    game = get_game("chess")
    fen = "8/8/8/4k3/8/3K4/4P3/8 w - - 0 1"
    # La seconda mossa è illegale (re adiacenti): la linea si ferma al prefisso valido.
    assert san_line(game, ["e2e4", "e5d4"], start_fen=fen) == ["e4"]
    # Storico non ricostruibile dalla prima mossa: prefisso vuoto, mai un errore.
    assert san_line(game, ["a7a8"], start_fen=fen) == []
