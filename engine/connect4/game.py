"""Forza 4 (Connect Four): regole del gioco.

Due giocatori, 0 = X e 1 = O. Una mossa è una **colonna** (0-6): la pedina cade nella
posizione libera più in basso. La griglia è una tupla di 42 celle (riga 0 in alto);
lo stato (immutabile) è in ``state.py``.
"""

from __future__ import annotations

from ..common.game import Game
from ..common.outcome import Outcome
from .state import Connect4State

ROWS = 6
COLS = 7
_CENTER = COLS // 2


def _index(row: int, col: int) -> int:
    return row * COLS + col


def _winning_lines() -> list[tuple[int, int, int, int]]:
    """Tutte le quaterne di celle allineate (orizzontali, verticali, diagonali)."""
    lines = []
    for r in range(ROWS):
        for c in range(COLS):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                cells = []
                for k in range(4):
                    rr, cc = r + dr * k, c + dc * k
                    if 0 <= rr < ROWS and 0 <= cc < COLS:
                        cells.append(_index(rr, cc))
                if len(cells) == 4:
                    lines.append(tuple(cells))
    return lines


_LINES = _winning_lines()


def _winner(board: tuple):
    for a, b, c, d in _LINES:
        v = board[a]
        if v is not None and v == board[b] == board[c] == board[d]:
            return v
    return None


class Connect4(Game):
    code = "connect4"
    name = "Forza 4"
    is_stochastic = False
    rows = ROWS
    cols = COLS
    move_type = "column"
    # Profondità del SOLO minimax generico di ripiego: il gioco ha un motore
    # dedicato (``engine_move``, bitboard + approfondimento iterativo) che il
    # giocatore locale usa sempre in via preferenziale.
    search_depth = 4

    def initial_state(self) -> Connect4State:
        return Connect4State(board=(None,) * (ROWS * COLS), current=0)

    def current_player(self, state: Connect4State) -> int:
        return state.current

    def legal_moves(self, state: Connect4State):
        if self.is_terminal(state):
            return []
        return [c for c in range(COLS) if state.board[_index(0, c)] is None]

    def apply(self, state: Connect4State, move: int) -> Connect4State:
        if not 0 <= move < COLS or state.board[_index(0, move)] is not None:
            raise ValueError("Mossa non valida: colonna piena o inesistente")
        board = list(state.board)
        for r in range(ROWS - 1, -1, -1):
            i = _index(r, move)
            if board[i] is None:
                board[i] = state.current
                break
        return Connect4State(board=tuple(board), current=1 - state.current)

    def is_terminal(self, state: Connect4State) -> bool:
        return _winner(state.board) is not None or all(c is not None for c in state.board)

    def outcome(self, state: Connect4State) -> Outcome:
        return Outcome(winner=_winner(state.board))

    def serialize_state(self, state: Connect4State) -> dict:
        return {"board": list(state.board), "current": state.current}

    def deserialize_state(self, data: dict) -> Connect4State:
        return Connect4State(board=tuple(data["board"]), current=data["current"])

    def render_text(self, state: Connect4State) -> str:
        sym = {0: "X", 1: "O", None: "."}
        return "\n".join(
            " ".join(sym[state.board[_index(r, c)]] for c in range(COLS)) for r in range(ROWS)
        )

    def describe_move(self, state: Connect4State, move: int) -> str:
        return str(move + 1)  # colonna in notazione 1-based

    def engine_move(
        self,
        state: Connect4State,
        history=None,
        time_limit=2.0,
        max_depth=None,
        style=None,
        jitter=0,
        tt=None,
        stop=None,
    ):
        """Mossa dal motore dedicato (bitboard, negamax iterativo con TT)."""
        from . import engine

        return engine.best_move(
            self,
            state,
            time_limit=time_limit,
            max_depth=max_depth,
            # Il jitter della piattaforma è in CENTIPEDONI scacchistici (100 = un
            # pedone); qui una casella vincente vale _SPOT=16: si riscala.
            jitter=jitter * 0.16,
            tt=tt,
            stop=stop,
        )

    def heuristic(self, state: Connect4State, player: int) -> float:
        board = state.board
        opp = 1 - player
        score = 0.0
        # Preferenza per il controllo della colonna centrale.
        score += sum(1 for r in range(ROWS) if board[_index(r, _CENTER)] == player) * 3
        for line in _LINES:
            vals = [board[i] for i in line]
            mine = vals.count(player)
            theirs = vals.count(opp)
            if mine and theirs:
                continue  # finestra bloccata
            if mine == 3:
                score += 50
            elif mine == 2:
                score += 10
            elif mine == 1:
                score += 1
            if theirs == 3:
                score -= 80  # blocca le minacce avversarie
            elif theirs == 2:
                score -= 10
            elif theirs == 1:
                score -= 1
        return score
