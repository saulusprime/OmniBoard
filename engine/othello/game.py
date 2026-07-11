"""Othello (Reversi): regole del gioco.

Due giocatori, 0 = Nero (muove per primo, come da regolamento) e 1 = Bianco.
Una mossa è una **cella** (0-63): la pedina si posa su una casella vuota che
imprigiona almeno una fila avversaria e la gira. Il **passo è automatico**:
se dopo una mossa l'avversario non ha giocate, il tratto torna a chi ha
appena mosso (il client non deve gestire il "passo" come mossa esplicita);
quando nessuno dei due può muovere la partita è finita e vince chi ha più
pedine. Lo stato (immutabile) è in ``state.py``.
"""

from __future__ import annotations

from ..common.game import Game
from ..common.outcome import Outcome
from .state import OthelloState

ROWS = 8
COLS = 8
_DIRS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
_FILES = "abcdefgh"

# Pesi posizionali classici: angoli d'oro, case X/C velenose accanto agli
# angoli, bordi buoni. Si scrive il quarto in alto a sinistra (4×4) e la
# scacchiera intera nasce per specchiatura: una sola riga di verità.
_Q = (
    (120, -20, 20, 5),
    (-20, -40, -5, -5),
    (20, -5, 15, 3),
    (5, -5, 3, 3),
)
_W = tuple(_Q[min(r, 7 - r)][min(c, 7 - c)] for r in range(8) for c in range(8))


def _flips(board: tuple, cell: int, player: int) -> list[int]:
    """Le pedine avversarie girate posando in ``cell``; vuota = mossa illegale."""
    if board[cell] is not None:
        return []
    r0, c0 = divmod(cell, COLS)
    opp = 1 - player
    out: list[int] = []
    for dr, dc in _DIRS:
        r, c = r0 + dr, c0 + dc
        line = []
        while 0 <= r < ROWS and 0 <= c < COLS and board[r * COLS + c] == opp:
            line.append(r * COLS + c)
            r += dr
            c += dc
        if line and 0 <= r < ROWS and 0 <= c < COLS and board[r * COLS + c] == player:
            out.extend(line)
    return out


def _moves_for(board: tuple, player: int) -> list[int]:
    return [i for i in range(64) if board[i] is None and _flips(board, i, player)]


class Othello(Game):
    code = "othello"
    name = "Othello"
    is_stochastic = False
    rows = ROWS
    cols = COLS
    move_type = "cell"
    search_depth = 4  # minimax generico + euristica posizionale (mobilità e angoli)

    def initial_state(self) -> OthelloState:
        board = [None] * 64
        board[27], board[36] = 1, 1  # d4, e5: Bianco
        board[28], board[35] = 0, 0  # e4, d5: Nero
        return OthelloState(board=tuple(board), current=0)

    def current_player(self, state: OthelloState) -> int:
        return state.current

    def legal_moves(self, state: OthelloState):
        return _moves_for(state.board, state.current)

    def apply(self, state: OthelloState, move: int) -> OthelloState:
        if not 0 <= move < 64:
            raise ValueError("Mossa non valida: casella fuori dalla scacchiera")
        flips = _flips(state.board, move, state.current)
        if not flips:
            raise ValueError("Mossa non valida: non gira nessuna pedina avversaria")
        board = list(state.board)
        board[move] = state.current
        for i in flips:
            board[i] = state.current
        board = tuple(board)
        # Passo automatico: tocca all'avversario solo se ha mosse; altrimenti il
        # tratto resta a chi ha mosso (se non ne ha nemmeno lui, è terminale).
        nxt = 1 - state.current
        if not _moves_for(board, nxt):
            nxt = state.current
        return OthelloState(board=board, current=nxt)

    def is_terminal(self, state: OthelloState) -> bool:
        return not _moves_for(state.board, 0) and not _moves_for(state.board, 1)

    def outcome(self, state: OthelloState) -> Outcome:
        blacks = sum(1 for v in state.board if v == 0)
        whites = sum(1 for v in state.board if v == 1)
        if blacks == whites:
            return Outcome(winner=None)
        return Outcome(winner=0 if blacks > whites else 1)

    # ----- Serializzazione e presentazione -----
    def serialize_state(self, state: OthelloState) -> dict:
        return {"board": list(state.board), "current": state.current}

    def deserialize_state(self, data: dict) -> OthelloState:
        return OthelloState(board=tuple(data["board"]), current=data["current"])

    def render_text(self, state: OthelloState) -> str:
        sym = {0: "●", 1: "○", None: "."}
        return "\n".join(
            " ".join(sym[state.board[r * COLS + c]] for c in range(COLS)) for r in range(ROWS)
        )

    def describe_move(self, state: OthelloState, move: int) -> str:
        r, c = divmod(move, COLS)
        return f"{_FILES[c]}{r + 1}"  # notazione Othello: a1 in alto a sinistra

    def view_board(self, state: OthelloState) -> list:
        symbols = {0: "●", 1: "○", None: None}  # Nero muove per primo (lato X)
        return [symbols[v] for v in state.board]

    def view_status(self, state: OthelloState) -> str | None:
        blacks = sum(1 for v in state.board if v == 0)
        whites = sum(1 for v in state.board if v == 1)
        return f"● {blacks} — ○ {whites}"

    def heuristic(self, state: OthelloState, player: int) -> float:
        board = state.board
        opp = 1 - player
        empties = sum(1 for v in board if v is None)
        mine = sum(1 for v in board if v == player)
        theirs = sum(1 for v in board if v == opp)
        # Finale: contano solo le pedine (la ricerca completa chiude i conti).
        if empties <= 10:
            return float((mine - theirs) * 20)
        pos = sum(
            _W[i] if board[i] == player else -_W[i] for i in range(64) if board[i] is not None
        )
        mobility = len(_moves_for(board, player)) - len(_moves_for(board, opp))
        return float(pos + 8 * mobility)
