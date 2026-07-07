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


def test_cannot_mate_flag_rule():
    """Art. 6.9: chi vince a tempo deve poter dare matto con QUALCHE serie di mosse."""
    # Re nudo: mai. K+N contro re nudo: mai. K+N contro QUALSIASI cosa: sì
    # (l'avversario collabora col blocco — o promuove un pedone per farlo).
    assert Chess.cannot_mate(_board({0: "k", 63: "K"}), 0) is True
    assert Chess.cannot_mate(_board({0: "k", 63: "K", 27: "N"}), 0) is True
    assert Chess.cannot_mate(_board({0: "k", 63: "K", 27: "N", 8: "r"}), 0) is False
    assert Chess.cannot_mate(_board({0: "k", 63: "K", 27: "N", 8: "p"}), 0) is False
    # Re + due cavalli: il matto d'aiuto esiste → può vincere a tempo.
    assert Chess.cannot_mate(_board({0: "k", 63: "K", 27: "N", 28: "N"}), 0) is False
    # Alfieri monotinta da entrambe le parti (27 e 48 = stessa tinta): mai matto.
    assert Chess.cannot_mate(_board({0: "k", 63: "K", 27: "B"}), 0) is True
    assert Chess.cannot_mate(_board({0: "k", 63: "K", 27: "B", 48: "b"}), 0) is True
    # Alfiere avversario su tinta DIVERSA (28): il blocco esiste → matto possibile.
    assert Chess.cannot_mate(_board({0: "k", 63: "K", 27: "B", 28: "b"}), 0) is False
    # Un pedone proprio: promuove → matto sempre possibile.
    assert Chess.cannot_mate(_board({0: "k", 63: "K", 27: "P"}), 0) is False
    # Il test vale per lato: il NERO con solo il re non può, il bianco pieno sì.
    assert Chess.cannot_mate(_board({0: "k", 63: "K", 27: "Q"}), 1) is True
    assert Chess.cannot_mate(_board({0: "k", 63: "K", 27: "Q"}), 0) is False
