"""Scacchiera: costanti e funzioni di base condivise da regole e motore.

Rappresentazione: board = tupla di 64 celle (riga 0 in alto = traversa 8). I pezzi sono
caratteri: maiuscolo = Bianco (0), minuscolo = Nero (1); ``KQRBNP`` / ``kqrbnp``.
"""

from __future__ import annotations

WHITE, BLACK = 0, 1

ROOK_DIRS = ((-1, 0), (1, 0), (0, -1), (0, 1))
BISHOP_DIRS = ((-1, -1), (-1, 1), (1, -1), (1, 1))
KING_DIRS = ROOK_DIRS + BISHOP_DIRS
KNIGHT_DIRS = ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1))

UNICODE_PIECES = {
    "K": "♔",
    "Q": "♕",
    "R": "♖",
    "B": "♗",
    "N": "♘",
    "P": "♙",
    "k": "♚",
    "q": "♛",
    "r": "♜",
    "b": "♝",
    "n": "♞",
    "p": "♟",
}
PIECE_VALUES = {"P": 100, "N": 320, "B": 330, "R": 500, "Q": 900, "K": 0}

# Indici delle case d'angolo (torri) per i diritti di arrocco.
A1, H1, A8, H8 = 56, 63, 0, 7


def on(r, c):
    """True se (riga, colonna) è dentro la scacchiera."""
    return 0 <= r < 8 and 0 <= c < 8


def coord(sq):
    """Nome algebrico della casella (0 = a8 … 63 = h1)."""
    r, c = divmod(sq, 8)
    return f"{chr(97 + c)}{8 - r}"


def color_of(piece):
    """Colore di un pezzo: WHITE se maiuscolo, BLACK se minuscolo."""
    return WHITE if piece.isupper() else BLACK


def initial_board() -> tuple:
    back = "RNBQKBNR"
    board: list[str | None] = [None] * 64
    for c in range(8):
        board[0 * 8 + c] = back[c].lower()  # Nero in alto
        board[1 * 8 + c] = "p"
        board[6 * 8 + c] = "P"
        board[7 * 8 + c] = back[c]  # Bianco in basso
    return tuple(board)


def king_square(board, color):
    try:
        return board.index("K" if color == WHITE else "k")
    except ValueError:
        return None


def is_attacked(board, sq, by_color):
    """True se la casella ``sq`` è attaccata da un pezzo del colore ``by_color``."""
    r, c = divmod(sq, 8)
    # Pedoni
    if by_color == WHITE:
        for dc in (-1, 1):
            rr, cc = r + 1, c + dc
            if on(rr, cc) and board[rr * 8 + cc] == "P":
                return True
    else:
        for dc in (-1, 1):
            rr, cc = r - 1, c + dc
            if on(rr, cc) and board[rr * 8 + cc] == "p":
                return True
    # Cavalli
    knight = "N" if by_color == WHITE else "n"
    for dr, dc in KNIGHT_DIRS:
        rr, cc = r + dr, c + dc
        if on(rr, cc) and board[rr * 8 + cc] == knight:
            return True
    # Re
    king = "K" if by_color == WHITE else "k"
    for dr, dc in KING_DIRS:
        rr, cc = r + dr, c + dc
        if on(rr, cc) and board[rr * 8 + cc] == king:
            return True
    # Pezzi che scorrono
    for dirs, kinds in ((BISHOP_DIRS, "BQ"), (ROOK_DIRS, "RQ")):
        pieces = kinds if by_color == WHITE else kinds.lower()
        for dr, dc in dirs:
            rr, cc = r + dr, c + dc
            while on(rr, cc):
                p = board[rr * 8 + cc]
                if p is not None:
                    if p in pieces:
                        return True
                    break
                rr += dr
                cc += dc
    return False
