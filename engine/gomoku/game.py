"""Gomoku (cinque in fila): regole del gioco.

Due giocatori, 0 = Nero (muove per primo) e 1 = Bianco, su un goban 15×15.
Una mossa è una **cella** (0-224): la pietra si posa su un'intersezione
libera. Vince chi allinea **cinque o più** pietre consecutive (variante
"freestyle": l'overline vale); goban pieno senza cinquine = patta. Lo stato
(immutabile) è in ``state.py``.
"""

from __future__ import annotations

from ..common.game import Game
from ..common.outcome import Outcome
from .state import GomokuState

ROWS = 15
COLS = 15
_FILES = "abcdefghijklmno"
_DIRS = ((0, 1), (1, 0), (1, 1), (1, -1))


def _winner(board: tuple):
    """0 o 1 se sul goban c'è una fila di 5+; altrimenti None."""
    for i in range(ROWS * COLS):
        v = board[i]
        if v is None:
            continue
        r, c = divmod(i, COLS)
        for dr, dc in _DIRS:
            # Si conta solo dall'INIZIO della fila (la cella precedente differisce).
            pr, pc = r - dr, c - dc
            if 0 <= pr < ROWS and 0 <= pc < COLS and board[pr * COLS + pc] == v:
                continue
            n, rr, cc = 0, r, c
            while 0 <= rr < ROWS and 0 <= cc < COLS and board[rr * COLS + cc] == v:
                n += 1
                rr += dr
                cc += dc
            if n >= 5:
                return v
    return None


class Gomoku(Game):
    code = "gomoku"
    name = "Gomoku"
    is_stochastic = False
    rows = ROWS
    cols = COLS
    move_type = "cell"
    # Ripiego di emergenza del minimax generico: con 225 rami serve il motore
    # dedicato (``engine_move``), che il giocatore locale preferisce da solo.
    search_depth = 1

    def initial_state(self) -> GomokuState:
        return GomokuState(board=(None,) * (ROWS * COLS), current=0)

    def current_player(self, state: GomokuState) -> int:
        return state.current

    def legal_moves(self, state: GomokuState):
        if self.is_terminal(state):
            return []
        return [i for i, v in enumerate(state.board) if v is None]

    def apply(self, state: GomokuState, move: int) -> GomokuState:
        if not 0 <= move < ROWS * COLS or state.board[move] is not None:
            raise ValueError("Mossa non valida: intersezione occupata o fuori dal goban")
        board = list(state.board)
        board[move] = state.current
        return GomokuState(board=tuple(board), current=1 - state.current)

    def is_terminal(self, state: GomokuState) -> bool:
        return _winner(state.board) is not None or all(v is not None for v in state.board)

    def outcome(self, state: GomokuState) -> Outcome:
        return Outcome(winner=_winner(state.board))

    # ----- Serializzazione e presentazione -----
    def serialize_state(self, state: GomokuState) -> dict:
        return {"board": list(state.board), "current": state.current}

    def deserialize_state(self, data: dict) -> GomokuState:
        return GomokuState(board=tuple(data["board"]), current=data["current"])

    def render_text(self, state: GomokuState) -> str:
        sym = {0: "●", 1: "○", None: "."}
        return "\n".join(
            " ".join(sym[state.board[r * COLS + c]] for c in range(COLS)) for r in range(ROWS)
        )

    def describe_move(self, state: GomokuState, move: int) -> str:
        r, c = divmod(move, COLS)
        return f"{_FILES[c]}{r + 1}"

    def view_board(self, state: GomokuState) -> list:
        symbols = {0: "●", 1: "○", None: None}  # Nero muove per primo (lato X)
        return [symbols[v] for v in state.board]

    def engine_move(
        self,
        state: GomokuState,
        history=None,
        time_limit=2.0,
        max_depth=6,
        style=None,
        jitter=0,
        tt=None,
        stop=None,
    ):
        """Mossa dal motore dedicato (candidati vicini + alpha-beta iterativo)."""
        from . import engine

        # Il jitter della piattaforma è in CENTIPEDONI scacchistici (100 = un
        # pedone); qui un tre aperto vale ~128: la scala è già comparabile.
        return engine.best_move(
            self, state, time_limit=time_limit, max_depth=max_depth, jitter=jitter, stop=stop
        )

    def heuristic(self, state: GomokuState, player: int) -> float:
        """Valutazione leggera per il SOLO ripiego generico (finestra di 5)."""
        from . import engine

        return float(engine.static_score(state.board, player))
