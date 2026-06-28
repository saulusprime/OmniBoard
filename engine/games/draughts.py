"""Dama italiana (checkers): 8x8, si gioca sulle caselle scure, 12 pedine per parte.

Giocatori: 0 = Bianco (muove verso l'alto, riga 0) e 1 = Nero (verso il basso, riga 7).
Una casella è scura se ``(riga + colonna)`` è dispari. Una mossa è il **percorso** di
caselle (tupla di indici 0-63): partenza, poi gli atterraggi successivi.

Regole implementate (variante italiana):
- le pedine muovono/catturano solo **in avanti** in diagonale di una casella;
- la **dama** muove/cattura di una casella in tutte le diagonali (corto raggio, non volante);
- la **cattura è obbligatoria** e si deve prendere il **massimo numero di pezzi**;
- una **pedina non può catturare una dama**;
- la pedina che raggiunge l'ultima traversa diventa **dama** e la mossa termina.

Semplificazioni rispetto al regolamento FID completo: tra catture di pari numero non si
applicano le priorità fini (preferire la dama, catturare più dame, catturare prima le dame);
non è gestita la patta per ripetizione. Verranno affinate in seguito.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core import Game, Outcome

SIZE = 8

# Simboli Unicode: pedina/dama bianca e nera.
_WMAN, _WKING, _BMAN, _BKING = "⛀", "⛁", "⛂", "⛃"
_SYMBOL = {(0, False): _WMAN, (0, True): _WKING, (1, False): _BMAN, (1, True): _BKING}

_ALL4 = ((-1, -1), (-1, 1), (1, -1), (1, 1))
_FORWARD = {0: ((-1, -1), (-1, 1)), 1: ((1, -1), (1, 1))}  # avanti per Bianco / Nero


def _on(r: int, c: int) -> bool:
    return 0 <= r < SIZE and 0 <= c < SIZE


def _dark(r: int, c: int) -> bool:
    return (r + c) % 2 == 1


def _coord(sq: int) -> str:
    r, c = divmod(sq, SIZE)
    return f"{chr(97 + c)}{SIZE - r}"


@dataclass(frozen=True)
class DraughtsState:
    board: tuple  # 64 celle: None oppure (player, king)
    current: int


def _initial_board() -> tuple:
    board = [None] * (SIZE * SIZE)
    for r in range(SIZE):
        for c in range(SIZE):
            if not _dark(r, c):
                continue
            if r <= 2:
                board[r * SIZE + c] = (1, False)  # Nero in alto
            elif r >= 5:
                board[r * SIZE + c] = (0, False)  # Bianco in basso
    return tuple(board)


class Draughts(Game):
    code = "checkers"
    name = "Dama italiana"
    is_stochastic = False
    rows = SIZE
    cols = SIZE
    move_type = "draughts"
    search_depth = 4

    def initial_state(self) -> DraughtsState:
        return DraughtsState(board=_initial_board(), current=0)

    def current_player(self, state: DraughtsState) -> int:
        return state.current

    # ----- Generazione mosse -----
    def _capture_paths(self, board: tuple, start: int, piece) -> list[list[int]]:
        player, king = piece
        results: list[list[int]] = []

        def rec(b, sq, king_flag, path):
            r, c = divmod(sq, SIZE)
            dirs = _ALL4 if king_flag else _FORWARD[player]
            extended = False
            for dr, dc in dirs:
                jr, jc, lr, lc = r + dr, c + dc, r + 2 * dr, c + 2 * dc
                if not _on(lr, lc):
                    continue
                j, land = jr * SIZE + jc, lr * SIZE + lc
                if b[land] is not None:
                    continue
                target = b[j]
                if target is None or target[0] == player:
                    continue
                if not king_flag and target[1]:
                    continue  # una pedina non cattura una dama
                extended = True
                promote = not king_flag and ((player == 0 and lr == 0) or (player == 1 and lr == 7))
                nb = list(b)
                nb[sq] = None
                nb[j] = None
                nb[land] = (player, king_flag or promote)
                if promote:
                    results.append(path + [land])  # la promozione termina la mossa
                else:
                    rec(tuple(nb), land, king_flag, path + [land])
            if not extended and path:
                results.append(path)

        rec(board, start, king, [])
        return results

    def _all_captures(self, state: DraughtsState) -> list[tuple]:
        moves = []
        for sq, piece in enumerate(state.board):
            if piece is None or piece[0] != state.current:
                continue
            for path in self._capture_paths(state.board, sq, piece):
                moves.append((sq, *path))
        return moves

    def _simple_moves(self, state: DraughtsState) -> list[tuple]:
        moves = []
        for sq, piece in enumerate(state.board):
            if piece is None or piece[0] != state.current:
                continue
            r, c = divmod(sq, SIZE)
            dirs = _ALL4 if piece[1] else _FORWARD[state.current]
            for dr, dc in dirs:
                nr, nc = r + dr, c + dc
                if _on(nr, nc) and state.board[nr * SIZE + nc] is None:
                    moves.append((sq, nr * SIZE + nc))
        return moves

    def legal_moves(self, state: DraughtsState) -> list[tuple]:
        captures = self._all_captures(state)
        if captures:
            best = max(len(p) - 1 for p in captures)  # massimo numero di prese
            return [p for p in captures if len(p) - 1 == best]
        return self._simple_moves(state)

    def apply(self, state: DraughtsState, move: tuple) -> DraughtsState:
        board = list(state.board)
        player = state.current
        start = move[0]
        piece = board[start]
        if piece is None or piece[0] != player:
            raise ValueError("Mossa non valida: nessun pezzo proprio nella casella di partenza")
        _player, king = piece
        board[start] = None
        for a, b in zip(move, move[1:]):
            ar, ac = divmod(a, SIZE)
            br, bc = divmod(b, SIZE)
            if abs(br - ar) == 2:  # cattura: rimuovi il pezzo scavalcato
                board[(ar + br) // 2 * SIZE + (ac + bc) // 2] = None
        end = move[-1]
        er = end // SIZE
        promote = not king and ((player == 0 and er == 0) or (player == 1 and er == 7))
        board[end] = (player, king or promote)
        return DraughtsState(board=tuple(board), current=1 - player)

    def is_terminal(self, state: DraughtsState) -> bool:
        return len(self.legal_moves(state)) == 0

    def outcome(self, state: DraughtsState) -> Outcome:
        # Stato terminale: il giocatore di turno non può muovere e perde.
        return Outcome(winner=1 - state.current)

    # ----- Serializzazione / presentazione -----
    def serialize_state(self, state: DraughtsState) -> dict:
        board = [list(cell) if cell is not None else None for cell in state.board]
        return {"board": board, "current": state.current}

    def deserialize_state(self, data: dict) -> DraughtsState:
        board = tuple(
            (cell[0], bool(cell[1])) if cell is not None else None for cell in data["board"]
        )
        return DraughtsState(board=board, current=data["current"])

    def view_board(self, state: DraughtsState) -> list:
        return [_SYMBOL[(cell[0], cell[1])] if cell is not None else None for cell in state.board]

    def move_id(self, move: tuple) -> str:
        return "-".join(str(s) for s in move)

    def describe_move(self, state: DraughtsState, move: tuple) -> str:
        is_capture = any(
            abs(divmod(b, SIZE)[0] - divmod(a, SIZE)[0]) == 2 for a, b in zip(move, move[1:])
        )
        sep = "x" if is_capture else "-"
        return sep.join(_coord(s) for s in move)

    def legal_moves_view(self, state: DraughtsState) -> list[dict]:
        return [
            {
                "id": self.move_id(move),
                "from": move[0],
                "to": move[-1],
                "changes": self.board_changes(state, move),
            }
            for move in self.legal_moves(state)
        ]

    def heuristic(self, state: DraughtsState, player: int) -> float:
        score = 0.0
        for sq, cell in enumerate(state.board):
            if cell is None:
                continue
            owner, king = cell
            value = 5.0 if king else 3.0
            if not king:  # bonus avanzamento verso la promozione
                r = sq // SIZE
                value += (7 - r if owner == 0 else r) * 0.1
            score += value if owner == player else -value
        return score
