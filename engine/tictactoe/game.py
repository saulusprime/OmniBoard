"""Tris (tic-tac-toe): regole del gioco.

Due giocatori, 0 = X (muove per primo) e 1 = O. La griglia 3x3 è rappresentata da
una tupla di 9 celle (0, 1 o None). Lo stato (immutabile) è in ``state.py``.
"""

from __future__ import annotations

from ..common.game import Game
from ..common.outcome import Outcome
from .state import TicTacToeState

# Le otto linee vincenti (indici di cella).
LINES = [
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
]

_SYMBOLS = {0: "X", 1: "O", None: "."}
_COLS = ("a", "b", "c")


def _winner(board: tuple):
    """Restituisce 0 o 1 se c'è un vincitore, altrimenti None."""
    for a, b, c in LINES:
        if board[a] is not None and board[a] == board[b] == board[c]:
            return board[a]
    return None


class TicTacToe(Game):
    code = "tictactoe"
    name = "Tris"
    is_stochastic = False
    rows = 3
    cols = 3
    move_type = "cell"

    def initial_state(self) -> TicTacToeState:
        return TicTacToeState(board=(None,) * 9, current=0)

    def current_player(self, state: TicTacToeState) -> int:
        return state.current

    def legal_moves(self, state: TicTacToeState):
        if self.is_terminal(state):
            return []
        return [i for i, cell in enumerate(state.board) if cell is None]

    def apply(self, state: TicTacToeState, move: int) -> TicTacToeState:
        if not 0 <= move < 9 or state.board[move] is not None:
            raise ValueError("Mossa non valida: casella occupata o fuori dalla griglia")
        board = list(state.board)
        board[move] = state.current
        return TicTacToeState(board=tuple(board), current=1 - state.current)

    def is_terminal(self, state: TicTacToeState) -> bool:
        return _winner(state.board) is not None or all(c is not None for c in state.board)

    def outcome(self, state: TicTacToeState) -> Outcome:
        return Outcome(winner=_winner(state.board))

    # ----- Serializzazione e presentazione -----
    def serialize_state(self, state: TicTacToeState) -> dict:
        return {"board": list(state.board), "current": state.current}

    def deserialize_state(self, data: dict) -> TicTacToeState:
        return TicTacToeState(board=tuple(data["board"]), current=data["current"])

    def render_text(self, state: TicTacToeState) -> str:
        b = [_SYMBOLS[c] for c in state.board]
        return f"{b[0]}|{b[1]}|{b[2]}\n{b[3]}|{b[4]}|{b[5]}\n{b[6]}|{b[7]}|{b[8]}"

    def describe_move(self, state: TicTacToeState, move: int) -> str:
        row, col = divmod(move, 3)
        return f"{_COLS[col]}{row + 1}"
