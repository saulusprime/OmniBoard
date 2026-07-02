"""Scacchi: regole complete (mosse legali, scacco/matto/stallo, arrocco, en passant,
promozione, regola delle 50 mosse, materiale insufficiente).

Rappresentazione: board = tupla di 64 celle (riga 0 in alto = traversa 8). I pezzi sono
caratteri: maiuscolo = Bianco (0), minuscolo = Nero (1); ``KQRBNP`` / ``kqrbnp``.
Una mossa è ``(from, to, promo)`` con ``promo`` None oppure in 'QRBN'. L'id è in stile UCI
(es. ``e2e4``, ``e7e8q``).

Semplificazione nota: non è gestita la patta per ripetizione (richiederebbe lo storico nello
stato). Sono gestite stallo, scacco matto, 50 mosse e materiale insufficiente.
"""

from __future__ import annotations

from typing import NamedTuple

from ..core import Game, Outcome
from . import openings

WHITE, BLACK = 0, 1

_ROOK_D = ((-1, 0), (1, 0), (0, -1), (0, 1))
_BISHOP_D = ((-1, -1), (-1, 1), (1, -1), (1, 1))
_KING_D = _ROOK_D + _BISHOP_D
_KNIGHT_D = ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1))

_UNICODE = {
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
_VALUE = {"P": 100, "N": 320, "B": 330, "R": 500, "Q": 900, "K": 0}

# Indici delle case d'angolo (torri) per i diritti di arrocco.
_A1, _H1, _A8, _H8 = 56, 63, 0, 7


def _on(r, c):
    return 0 <= r < 8 and 0 <= c < 8


def _coord(sq):
    r, c = divmod(sq, 8)
    return f"{chr(97 + c)}{8 - r}"


def _color(piece):
    return WHITE if piece.isupper() else BLACK


class ChessState(NamedTuple):
    # NamedTuple (non dataclass frozen): l'istanziazione è molto più veloce e `apply`
    # ne crea una per ogni nodo di ricerca del motore.
    board: tuple
    current: int
    castling: tuple  # (wK, wQ, bK, bQ)
    ep: int | None  # casa bersaglio dell'en passant
    halfmove: int  # contatore per la regola delle 50 mosse


def _initial_board() -> tuple:
    back = "RNBQKBNR"
    board: list[str | None] = [None] * 64
    for c in range(8):
        board[0 * 8 + c] = back[c].lower()  # Nero in alto
        board[1 * 8 + c] = "p"
        board[6 * 8 + c] = "P"
        board[7 * 8 + c] = back[c]  # Bianco in basso
    return tuple(board)


def _king_square(board, color):
    try:
        return board.index("K" if color == WHITE else "k")
    except ValueError:
        return None


def _is_attacked(board, sq, by_color):
    r, c = divmod(sq, 8)
    # Pedoni
    if by_color == WHITE:
        for dc in (-1, 1):
            rr, cc = r + 1, c + dc
            if _on(rr, cc) and board[rr * 8 + cc] == "P":
                return True
    else:
        for dc in (-1, 1):
            rr, cc = r - 1, c + dc
            if _on(rr, cc) and board[rr * 8 + cc] == "p":
                return True
    # Cavalli
    knight = "N" if by_color == WHITE else "n"
    for dr, dc in _KNIGHT_D:
        rr, cc = r + dr, c + dc
        if _on(rr, cc) and board[rr * 8 + cc] == knight:
            return True
    # Re
    king = "K" if by_color == WHITE else "k"
    for dr, dc in _KING_D:
        rr, cc = r + dr, c + dc
        if _on(rr, cc) and board[rr * 8 + cc] == king:
            return True
    # Pezzi che scorrono
    for dirs, kinds in ((_BISHOP_D, "BQ"), (_ROOK_D, "RQ")):
        pieces = kinds if by_color == WHITE else kinds.lower()
        for dr, dc in dirs:
            rr, cc = r + dr, c + dc
            while _on(rr, cc):
                p = board[rr * 8 + cc]
                if p is not None:
                    if p in pieces:
                        return True
                    break
                rr += dr
                cc += dc
    return False


class Chess(Game):
    code = "chess"
    name = "Scacchi"
    is_stochastic = False
    rows = 8
    cols = 8
    move_type = "chess"
    search_depth = 3

    def initial_state(self) -> ChessState:
        return ChessState(
            board=_initial_board(),
            current=WHITE,
            castling=(True, True, True, True),
            ep=None,
            halfmove=0,
        )

    @staticmethod
    def from_fen(fen: str) -> ChessState:
        """Costruisce uno stato da una stringa FEN (utile per test e analisi)."""
        parts = fen.split()
        rows = parts[0].split("/")
        board: list[str | None] = [None] * 64
        for r, row in enumerate(rows):
            c = 0
            for ch in row:
                if ch.isdigit():
                    c += int(ch)
                else:
                    board[r * 8 + c] = ch
                    c += 1
        current = WHITE if len(parts) < 2 or parts[1] == "w" else BLACK
        rights = parts[2] if len(parts) > 2 else "KQkq"
        castling = ("K" in rights, "Q" in rights, "k" in rights, "q" in rights)
        ep = None
        if len(parts) > 3 and parts[3] != "-":
            ep = (8 - int(parts[3][1])) * 8 + (ord(parts[3][0]) - 97)
        halfmove = int(parts[4]) if len(parts) > 4 else 0
        return ChessState(
            board=tuple(board), current=current, castling=castling, ep=ep, halfmove=halfmove
        )

    def current_player(self, state):
        return state.current

    # ----- Generazione mosse -----
    def _pseudo_moves(self, state):
        board = state.board
        color = state.current
        moves = []
        for sq, piece in enumerate(board):
            if piece is None or _color(piece) != color:
                continue
            r, c = divmod(sq, 8)
            kind = piece.upper()
            if kind == "P":
                self._pawn_moves(state, sq, r, c, color, moves)
            elif kind == "N":
                for dr, dc in _KNIGHT_D:
                    self._step(board, sq, r + dr, c + dc, color, moves)
            elif kind == "K":
                for dr, dc in _KING_D:
                    self._step(board, sq, r + dr, c + dc, color, moves)
                self._castling_moves(state, sq, r, c, color, moves)
            else:
                dirs = _BISHOP_D if kind == "B" else _ROOK_D if kind == "R" else _KING_D
                for dr, dc in dirs:
                    rr, cc = r + dr, c + dc
                    while _on(rr, cc):
                        dest = board[rr * 8 + cc]
                        if dest is None:
                            moves.append((sq, rr * 8 + cc, None))
                        else:
                            if _color(dest) != color:
                                moves.append((sq, rr * 8 + cc, None))
                            break
                        rr += dr
                        cc += dc
        return moves

    def _step(self, board, frm, rr, cc, color, moves):
        if not _on(rr, cc):
            return
        dest = board[rr * 8 + cc]
        if dest is None or _color(dest) != color:
            moves.append((frm, rr * 8 + cc, None))

    def _capture_moves(self, state):
        """Solo catture, promozioni ed en passant (per la quiescence del motore).

        Genera molto meno di ``_pseudo_moves``: nella ricerca di quiete le mosse
        tranquille non servono, e la loro generazione dominava il tempo del motore.
        """
        board = state.board
        color = state.current
        moves = []
        for sq, piece in enumerate(board):
            if piece is None or _color(piece) != color:
                continue
            r, c = divmod(sq, 8)
            kind = piece.upper()
            if kind == "P":
                direction = -1 if color == WHITE else 1
                last_row = 0 if color == WHITE else 7
                nr = r + direction
                if not 0 <= nr < 8:
                    continue
                if nr == last_row and board[nr * 8 + c] is None:  # spinta di promozione
                    for promo in ("Q", "R", "B", "N"):
                        moves.append((sq, nr * 8 + c, promo))
                for dc in (-1, 1):
                    cc = c + dc
                    if not 0 <= cc < 8:
                        continue
                    to = nr * 8 + cc
                    dest = board[to]
                    if dest is not None and _color(dest) != color:
                        if nr == last_row:
                            for promo in ("Q", "R", "B", "N"):
                                moves.append((sq, to, promo))
                        else:
                            moves.append((sq, to, None))
                    elif to == state.ep:
                        moves.append((sq, to, None))
            elif kind in ("N", "K"):
                for dr, dc in _KNIGHT_D if kind == "N" else _KING_D:
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < 8 and 0 <= cc < 8:
                        dest = board[rr * 8 + cc]
                        if dest is not None and _color(dest) != color:
                            moves.append((sq, rr * 8 + cc, None))
            else:
                dirs = _BISHOP_D if kind == "B" else _ROOK_D if kind == "R" else _KING_D
                for dr, dc in dirs:
                    rr, cc = r + dr, c + dc
                    while 0 <= rr < 8 and 0 <= cc < 8:
                        dest = board[rr * 8 + cc]
                        if dest is not None:
                            if _color(dest) != color:
                                moves.append((sq, rr * 8 + cc, None))
                            break
                        rr += dr
                        cc += dc
        return moves

    def _pawn_moves(self, state, sq, r, c, color, moves):
        board = state.board
        direction = -1 if color == WHITE else 1
        start_row = 6 if color == WHITE else 1
        last_row = 0 if color == WHITE else 7

        def add(frm, to):
            if to // 8 == last_row:
                for promo in ("Q", "R", "B", "N"):
                    moves.append((frm, to, promo))
            else:
                moves.append((frm, to, None))

        nr = r + direction
        if _on(nr, c) and board[nr * 8 + c] is None:
            add(sq, nr * 8 + c)
            if r == start_row and board[(r + 2 * direction) * 8 + c] is None:
                moves.append((sq, (r + 2 * direction) * 8 + c, None))
        for dc in (-1, 1):
            cc = c + dc
            if not _on(nr, cc):
                continue
            to = nr * 8 + cc
            dest = board[to]
            if dest is not None and _color(dest) != color:
                add(sq, to)
            elif to == state.ep:
                moves.append((sq, to, None))  # en passant

    def _castling_moves(self, state, sq, r, c, color, moves):
        board = state.board
        wK, wQ, bK, bQ = state.castling
        if _is_attacked(board, sq, 1 - color):
            return  # non si arrocca sotto scacco
        if color == WHITE and r == 7 and c == 4:
            if wK and board[61] is None and board[62] is None and board[63] == "R":
                if not _is_attacked(board, 61, BLACK) and not _is_attacked(board, 62, BLACK):
                    moves.append((sq, 62, None))
            if (
                wQ
                and board[59] is None
                and board[58] is None
                and board[57] is None
                and board[56] == "R"
            ):
                if not _is_attacked(board, 59, BLACK) and not _is_attacked(board, 58, BLACK):
                    moves.append((sq, 58, None))
        elif color == BLACK and r == 0 and c == 4:
            if bK and board[5] is None and board[6] is None and board[7] == "r":
                if not _is_attacked(board, 5, WHITE) and not _is_attacked(board, 6, WHITE):
                    moves.append((sq, 6, None))
            if (
                bQ
                and board[3] is None
                and board[2] is None
                and board[1] is None
                and board[0] == "r"
            ):
                if not _is_attacked(board, 3, WHITE) and not _is_attacked(board, 2, WHITE):
                    moves.append((sq, 2, None))

    def legal_moves(self, state):
        color = state.current
        legal = []
        for move in self._pseudo_moves(state):
            after = self.apply(state, move)
            ksq = _king_square(after.board, color)
            if ksq is not None and not _is_attacked(after.board, ksq, 1 - color):
                legal.append(move)
        return legal

    def apply(self, state, move):
        frm, to, promo = move
        board = list(state.board)
        piece = board[frm]
        color = state.current
        kind = piece.upper()
        castling = list(state.castling)
        fr, fc = divmod(frm, 8)
        tr, tc = divmod(to, 8)
        capture = board[to] is not None

        if kind == "P" and to == state.ep and fc != tc and board[to] is None:
            board[fr * 8 + tc] = None  # cattura en passant
            capture = True

        board[frm] = None
        if promo:
            board[to] = promo if color == WHITE else promo.lower()
        else:
            board[to] = piece

        if kind == "K" and abs(tc - fc) == 2:  # arrocco: muovi anche la torre
            if tc > fc:
                board[fr * 8 + 5], board[fr * 8 + 7] = board[fr * 8 + 7], None
            else:
                board[fr * 8 + 3], board[fr * 8 + 0] = board[fr * 8 + 0], None

        if kind == "K":
            if color == WHITE:
                castling[0] = castling[1] = False
            else:
                castling[2] = castling[3] = False
        for square in (frm, to):  # torre mossa o catturata nella sua casa
            if square == _H1:
                castling[0] = False
            elif square == _A1:
                castling[1] = False
            elif square == _H8:
                castling[2] = False
            elif square == _A8:
                castling[3] = False

        ep = (fr + tr) // 2 * 8 + fc if kind == "P" and abs(tr - fr) == 2 else None
        halfmove = 0 if (kind == "P" or capture) else state.halfmove + 1
        return ChessState(
            board=tuple(board),
            current=1 - color,
            castling=tuple(castling),
            ep=ep,
            halfmove=halfmove,
        )

    def _in_check(self, state, color):
        ksq = _king_square(state.board, color)
        return ksq is not None and _is_attacked(state.board, ksq, 1 - color)

    @staticmethod
    def _insufficient(board):
        others = [p.upper() for p in board if p and p.upper() != "K"]
        if not others:
            return True
        if len(others) == 1 and others[0] in ("N", "B"):
            return True
        return len(others) == 2 and all(o == "B" for o in others)

    def is_terminal(self, state):
        if state.halfmove >= 100 or self._insufficient(state.board):
            return True
        return len(self.legal_moves(state)) == 0

    def outcome(self, state):
        if self.legal_moves(state):
            return Outcome(winner=None)  # patta (50 mosse / materiale)
        if self._in_check(state, state.current):
            return Outcome(winner=1 - state.current)  # scacco matto
        return Outcome(winner=None)  # stallo

    # ----- Serializzazione / presentazione -----
    def serialize_state(self, state):
        return {
            "board": list(state.board),
            "current": state.current,
            "castling": list(state.castling),
            "ep": state.ep,
            "halfmove": state.halfmove,
        }

    def deserialize_state(self, data):
        return ChessState(
            board=tuple(data["board"]),
            current=data["current"],
            castling=tuple(data["castling"]),
            ep=data["ep"],
            halfmove=data["halfmove"],
        )

    def view_board(self, state):
        return [_UNICODE[p] if p else None for p in state.board]

    def render_text(self, state):
        rows = []
        for r in range(8):
            rows.append(" ".join(state.board[r * 8 + c] or "." for c in range(8)))
        return "\n".join(rows)

    def move_id(self, move):
        frm, to, promo = move
        return _coord(frm) + _coord(to) + (promo.lower() if promo else "")

    def describe_move(self, state, move):
        frm, to, promo = move
        piece = state.board[frm]
        kind = piece.upper()
        fc, tc = frm % 8, to % 8
        if kind == "K" and abs(tc - fc) == 2:
            text = "O-O" if tc > fc else "O-O-O"
        else:
            capture = state.board[to] is not None or (kind == "P" and to == state.ep)
            letter = "" if kind == "P" else kind
            text = f"{letter}{_coord(frm)}{'x' if capture else '-'}{_coord(to)}"
            if promo:
                text += f"={promo}"
        after = self.apply(state, move)
        if self._in_check(after, after.current):
            text += "#" if not self.legal_moves(after) else "+"
        return text

    def legal_moves_view(self, state):
        views = []
        for move in self.legal_moves(state):
            views.append(
                {
                    "id": self.move_id(move),
                    "from": move[0],
                    "to": move[1],
                    "changes": self.board_changes(state, move),
                }
            )
        return views

    def engine_move(self, state, history=None, time_limit=2.0, max_depth=64, style=None, jitter=0):
        """Mossa scelta dal motore di ricerca dedicato (alpha-beta + quiescence + TT).

        È molto più forte del minimax generico: analizza la scacchiera in profondità
        mossa dopo mossa, entro un budget di tempo. ``style`` modula il gioco in base al
        profilo dell'avversario (schemi/debolezze); ``jitter`` varia tra partite.
        """
        from . import chess_engine

        return chess_engine.best_move(
            self,
            state,
            history=history,
            time_limit=time_limit,
            max_depth=max_depth,
            style=style,
            jitter=jitter,
        )

    def opening_move(self, state, history):
        uci = openings.book_move(history or [])
        if not uci:
            return None
        for move in self.legal_moves(state):
            if self.move_id(move) == uci:
                return move
        return None

    def opening_name(self, history):
        return openings.detect_opening(history or [])

    def heuristic(self, state, player):
        score = 0
        for sq, piece in enumerate(state.board):
            if piece is None:
                continue
            value = _VALUE[piece.upper()]
            r, c = divmod(sq, 8)
            # Bonus posizionale leggero: centralità.
            value += (3 - abs(3.5 - c) - abs(3.5 - r)) * 2
            score += value if _color(piece) == player else -value
        return score
