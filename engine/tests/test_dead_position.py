"""Test della patta per posizione morta (FIDE 5.2.2) sui casi limite del materiale."""

from engine.chess.game import Chess


def _board(pieces: dict[int, str]) -> tuple:
    board = [None] * 64
    for sq, piece in pieces.items():
        board[sq] = piece
    return tuple(board)


def test_dead_material_cases():
    # Re contro Re, Re+minore contro Re: morte.
    assert Chess._insufficient(_board({0: "k", 63: "K"})) is True
    assert Chess._insufficient(_board({0: "k", 63: "K", 27: "B"})) is True
    assert Chess._insufficient(_board({0: "k", 63: "K", 27: "N"})) is True


def test_bishop_tints_decide():
    # Tinte: indice 27 (riga 3, col 3) → (3+3)%2 = 0; indice 28 (riga 3, col 4)
    # → (3+4)%2 = 1; indice 48 (riga 6, col 0) → 0. Quindi 27/28 = tinte DIVERSE,
    # 27/48 = STESSA tinta.
    # Coppia di alfieri (stesso proprietario, tinte diverse): matto FORZATO → viva.
    assert Chess._insufficient(_board({0: "k", 63: "K", 27: "B", 28: "B"})) is False
    # Alfieri contrapposti su tinte diverse: matto d'aiuto possibile → viva.
    assert Chess._insufficient(_board({0: "k", 63: "K", 27: "B", 28: "b"})) is False
    # Alfieri (anche di entrambi i lati) TUTTI sulla stessa tinta: morta.
    assert Chess._insufficient(_board({0: "k", 63: "K", 27: "B", 48: "b"})) is True
    assert Chess._insufficient(_board({0: "k", 63: "K", 27: "B", 48: "B"})) is True


def test_helpmate_material_stays_alive():
    # Re+2 Cavalli vs Re: per la FIDE NON è posizione morta (matto d'aiuto).
    assert Chess._insufficient(_board({0: "k", 63: "K", 27: "N", 36: "N"})) is False
    # Un pedone in giro = mai morta per materiale (può promuovere).
    assert Chess._insufficient(_board({0: "k", 63: "K", 27: "P"})) is False
