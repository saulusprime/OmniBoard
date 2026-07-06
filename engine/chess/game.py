"""Scacchi: regole complete (mosse legali, scacco/matto/stallo, arrocco, en passant,
promozione, regola delle 50 mosse, materiale insufficiente).

Una mossa è ``(from, to, promo)`` con ``promo`` None oppure in 'QRBN'. L'id è in stile UCI
(es. ``e2e4``, ``e7e8q``). La rappresentazione della scacchiera e le funzioni di base sono
in ``board.py``; lo stato immutabile in ``state.py``; il motore di ricerca in ``engine.py``.

Semplificazione nota: non è gestita la patta per ripetizione (richiederebbe lo storico nello
stato). Sono gestite stallo, scacco matto, 50 mosse e materiale insufficiente.
"""

from __future__ import annotations

import random

from ..common.game import Game
from ..common.outcome import Outcome
from . import openings
from .board import (
    A1,
    A8,
    BISHOP_DIRS,
    BLACK,
    H1,
    H8,
    KING_DIRS,
    KNIGHT_DIRS,
    PIECE_VALUES,
    ROOK_DIRS,
    UNICODE_PIECES,
    WHITE,
    color_of,
    coord,
    initial_board,
    is_attacked,
    king_square,
    on,
)
from .state import ChessState


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
            board=initial_board(),
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

    @staticmethod
    def to_fen(state) -> str:
        """Stringa FEN dello stato (inverso di ``from_fen``; usata dal ponte UCI).

        Il numero di mossa non è tracciato nello stato: si emette ``1``, sufficiente
        per i motori UCI (usano il contatore solo per informazione).
        """
        rows = []
        for r in range(8):
            row = ""
            empty = 0
            for c in range(8):
                piece = state.board[r * 8 + c]
                if piece is None:
                    empty += 1
                else:
                    if empty:
                        row += str(empty)
                        empty = 0
                    row += piece
            if empty:
                row += str(empty)
            rows.append(row)
        wk, wq, bk, bq = state.castling
        rights = (
            ("K" if wk else "") + ("Q" if wq else "") + ("k" if bk else "") + ("q" if bq else "")
        )
        ep = coord(state.ep) if state.ep is not None else "-"
        side = "w" if state.current == WHITE else "b"
        return f"{'/'.join(rows)} {side} {rights or '-'} {ep} {state.halfmove} 1"

    def current_player(self, state):
        return state.current

    # ----- Generazione mosse -----
    def _pseudo_moves(self, state):
        board = state.board
        color = state.current
        moves = []
        for sq, piece in enumerate(board):
            if piece is None or color_of(piece) != color:
                continue
            r, c = divmod(sq, 8)
            kind = piece.upper()
            if kind == "P":
                self._pawn_moves(state, sq, r, c, color, moves)
            elif kind == "N":
                for dr, dc in KNIGHT_DIRS:
                    self._step(board, sq, r + dr, c + dc, color, moves)
            elif kind == "K":
                for dr, dc in KING_DIRS:
                    self._step(board, sq, r + dr, c + dc, color, moves)
                self._castling_moves(state, sq, r, c, color, moves)
            else:
                dirs = BISHOP_DIRS if kind == "B" else ROOK_DIRS if kind == "R" else KING_DIRS
                for dr, dc in dirs:
                    rr, cc = r + dr, c + dc
                    while on(rr, cc):
                        dest = board[rr * 8 + cc]
                        if dest is None:
                            moves.append((sq, rr * 8 + cc, None))
                        else:
                            if color_of(dest) != color:
                                moves.append((sq, rr * 8 + cc, None))
                            break
                        rr += dr
                        cc += dc
        return moves

    def _step(self, board, frm, rr, cc, color, moves):
        if not on(rr, cc):
            return
        dest = board[rr * 8 + cc]
        if dest is None or color_of(dest) != color:
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
            if piece is None or color_of(piece) != color:
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
                    if dest is not None and color_of(dest) != color:
                        if nr == last_row:
                            for promo in ("Q", "R", "B", "N"):
                                moves.append((sq, to, promo))
                        else:
                            moves.append((sq, to, None))
                    elif to == state.ep:
                        moves.append((sq, to, None))
            elif kind in ("N", "K"):
                for dr, dc in KNIGHT_DIRS if kind == "N" else KING_DIRS:
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < 8 and 0 <= cc < 8:
                        dest = board[rr * 8 + cc]
                        if dest is not None and color_of(dest) != color:
                            moves.append((sq, rr * 8 + cc, None))
            else:
                dirs = BISHOP_DIRS if kind == "B" else ROOK_DIRS if kind == "R" else KING_DIRS
                for dr, dc in dirs:
                    rr, cc = r + dr, c + dc
                    while 0 <= rr < 8 and 0 <= cc < 8:
                        dest = board[rr * 8 + cc]
                        if dest is not None:
                            if color_of(dest) != color:
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
        if on(nr, c) and board[nr * 8 + c] is None:
            add(sq, nr * 8 + c)
            if r == start_row and board[(r + 2 * direction) * 8 + c] is None:
                moves.append((sq, (r + 2 * direction) * 8 + c, None))
        for dc in (-1, 1):
            cc = c + dc
            if not on(nr, cc):
                continue
            to = nr * 8 + cc
            dest = board[to]
            if dest is not None and color_of(dest) != color:
                add(sq, to)
            elif to == state.ep:
                moves.append((sq, to, None))  # en passant

    def _castling_moves(self, state, sq, r, c, color, moves):
        board = state.board
        wK, wQ, bK, bQ = state.castling
        if is_attacked(board, sq, 1 - color):
            return  # non si arrocca sotto scacco
        if color == WHITE and r == 7 and c == 4:
            if wK and board[61] is None and board[62] is None and board[63] == "R":
                if not is_attacked(board, 61, BLACK) and not is_attacked(board, 62, BLACK):
                    moves.append((sq, 62, None))
            if (
                wQ
                and board[59] is None
                and board[58] is None
                and board[57] is None
                and board[56] == "R"
            ):
                if not is_attacked(board, 59, BLACK) and not is_attacked(board, 58, BLACK):
                    moves.append((sq, 58, None))
        elif color == BLACK and r == 0 and c == 4:
            if bK and board[5] is None and board[6] is None and board[7] == "r":
                if not is_attacked(board, 5, WHITE) and not is_attacked(board, 6, WHITE):
                    moves.append((sq, 6, None))
            if (
                bQ
                and board[3] is None
                and board[2] is None
                and board[1] is None
                and board[0] == "r"
            ):
                if not is_attacked(board, 3, WHITE) and not is_attacked(board, 2, WHITE):
                    moves.append((sq, 2, None))

    def legal_moves(self, state):
        color = state.current
        legal = []
        for move in self._pseudo_moves(state):
            after = self.apply(state, move)
            ksq = king_square(after.board, color)
            if ksq is not None and not is_attacked(after.board, ksq, 1 - color):
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
            if square == H1:
                castling[0] = False
            elif square == A1:
                castling[1] = False
            elif square == H8:
                castling[2] = False
            elif square == A8:
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
        ksq = king_square(state.board, color)
        return ksq is not None and is_attacked(state.board, ksq, 1 - color)

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
        return [UNICODE_PIECES[p] if p else None for p in state.board]

    def render_text(self, state):
        rows = []
        for r in range(8):
            rows.append(" ".join(state.board[r * 8 + c] or "." for c in range(8)))
        return "\n".join(rows)

    def move_id(self, move):
        frm, to, promo = move
        return coord(frm) + coord(to) + (promo.lower() if promo else "")

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
            text = f"{letter}{coord(frm)}{'x' if capture else '-'}{coord(to)}"
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
        from . import engine

        return engine.best_move(
            self,
            state,
            history=history,
            time_limit=time_limit,
            max_depth=max_depth,
            style=style,
            jitter=jitter,
        )

    # Libro delle aperture indicizzato PER POSIZIONE (costruito pigramente una volta):
    # le continuazioni valgono anche quando la posizione è raggiunta per trasposizione
    # (ordine di mosse diverso). I duplicati pesano la scelta casuale.
    _book: dict | None = None

    @classmethod
    def reset_book_cache(cls) -> None:
        """Invalida gli indici dei libri (dopo aver cambiato ``CHESS_BOOK_FILE``
        o ``CHESS_POLYGLOT_BOOK``)."""
        cls._book = None
        from . import polyglot

        polyglot.reset_cache()

    def _position_book(self) -> dict:
        if Chess._book is None:
            # Ogni continuazione ricorda il NOME della sua linea: serve alle
            # aperture-bersaglio (preferire le linee in cui l'avversario rende male).
            book: dict[tuple, list[tuple[str, str]]] = {}
            for name, line in openings.all_lines():
                state = self.initial_state()
                for uci in line:
                    move = next(
                        (m for m in self._pseudo_moves(state) if self.move_id(m) == uci), None
                    )
                    if move is None:
                        break  # mossa non valida (file utente): si tiene il prefisso valido
                    key = (state.board, state.current, state.castling, state.ep)
                    book.setdefault(key, []).append((uci, name))
                    state = self.apply(state, move)
            Chess._book = book
        return Chess._book

    @staticmethod
    def _matches_target(line_name: str, targets) -> bool:
        """La linea appartiene a un'apertura bersaglio? (confronto per sottostringa,
        nei due sensi: «Difesa Siciliana» aggancia anche le sue varianti nominate)."""
        name = line_name.lower()
        return any(t.lower() in name or name in t.lower() for t in targets if t)

    def opening_move(self, state, history, prefer=None):
        """Mossa dal libro; con ``prefer`` (nomi di aperture) si fa APERTURA-BERSAGLIO:
        tra le continuazioni disponibili si scelgono solo quelle che portano nelle
        linee indicate (tipicamente le più deboli nel profilo dell'avversario);
        se nessuna corrisponde si torna alla scelta normale su tutto il libro.
        """
        candidates = self._position_book().get(
            (state.board, state.current, state.castling, state.ep)
        )
        if not candidates:
            # Libro Polyglot (.bin, CHESS_POLYGLOT_BOOK): probing per chiave
            # Zobrist, scelta pesata. Non ha nomi di linee: niente bersagli.
            from . import polyglot

            uci = polyglot.weighted_choice(polyglot.probe(state))
            if uci:
                for move in self.legal_moves(state):
                    if self.move_id(move) == uci:
                        return move
            return None
        if prefer:
            targeted = [c for c in candidates if self._matches_target(c[1], prefer)]
            if targeted:
                candidates = targeted
        uci = random.choice(candidates)[0]
        for move in self.legal_moves(state):
            if self.move_id(move) == uci:
                return move
        return None

    def is_repetition_draw(self, history) -> bool:
        """Patta per TRIPLICE RIPETIZIONE: la posizione corrente (dopo l'ultima
        mossa dello storico) si è già presentata almeno tre volte.

        La chiave di posizione è (scacchiera, tratto, diritti di arrocco, casa
        en passant) — le stesse componenti del libro: due posizioni contano come
        "uguali" solo se anche i diritti speciali coincidono, come da regolamento
        FIDE. Si rigioca lo storico dalla posizione iniziale (puro, O(n) a chiamata).
        """
        if not history or len(history) < 8:  # servono almeno 4 mosse per parte
            return False
        counts: dict[tuple, int] = {}
        state = self.initial_state()
        key = (state.board, state.current, state.castling, state.ep)
        counts[key] = 1
        for uci in history:
            move = next((m for m in self._pseudo_moves(state) if self.move_id(m) == uci), None)
            if move is None:
                return False  # storico non ricostruibile: nessuna dichiarazione
            state = self.apply(state, move)
            key = (state.board, state.current, state.castling, state.ep)
            counts[key] = counts.get(key, 0) + 1
        return counts[key] >= 3

    def opening_name(self, history):
        return openings.detect_opening(history or [])

    def heuristic(self, state, player):
        score = 0
        for sq, piece in enumerate(state.board):
            if piece is None:
                continue
            value = PIECE_VALUES[piece.upper()]
            r, c = divmod(sq, 8)
            # Bonus posizionale leggero: centralità.
            value += (3 - abs(3.5 - c) - abs(3.5 - r)) * 2
            score += value if color_of(piece) == player else -value
        return score
