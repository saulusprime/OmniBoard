"""Interfaccia astratta di un gioco a turni per due giocatori.

Definisce il contratto che ogni gioco concreto implementa nella propria directory
(es. ``engine/tictactoe/``, ``engine/chess/``). È previsto un *hook* per i nodi del
caso (dadi), non ancora usato, così da poter aggiungere in futuro giochi stocastici
come il backgammon.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, Sequence, TypeVar

from .outcome import Outcome, Player

S = TypeVar("S")  # tipo dello stato di gioco
M = TypeVar("M")  # tipo della mossa


class Game(ABC, Generic[S, M]):
    """Interfaccia astratta di un gioco a turni a informazione perfetta.

    Lo stato è trattato come immutabile: ``apply`` restituisce un nuovo stato.
    """

    code: str = ""
    name: str = ""
    is_stochastic: bool = False
    # Geometria del tavoliere e tipo di mossa, usati dal frontend per il rendering.
    rows: int = 0
    cols: int = 0
    move_type: str = "cell"  # "cell" (clic sulla casella) | "column" (caduta nella colonna)
    # Profondità di ricerca per l'IA locale: None = ricerca completa fino al termine
    # (adatta a giochi piccoli come il Tris); un intero limita la profondità e usa
    # ``heuristic`` (necessario per giochi grandi come Forza 4).
    search_depth: int | None = None

    @abstractmethod
    def initial_state(self) -> S:
        """Stato iniziale della partita."""

    @abstractmethod
    def current_player(self, state: S) -> Player:
        """Giocatore di turno nello stato dato."""

    @abstractmethod
    def legal_moves(self, state: S) -> Sequence[M]:
        """Elenco delle mosse legali nello stato dato."""

    @abstractmethod
    def apply(self, state: S, move: M) -> S:
        """Applica una mossa e restituisce il nuovo stato (senza mutare l'originale)."""

    @abstractmethod
    def is_terminal(self, state: S) -> bool:
        """True se lo stato è terminale (partita conclusa)."""

    @abstractmethod
    def outcome(self, state: S) -> Outcome:
        """Esito della partita; valido solo se ``is_terminal`` è True."""

    # ----- Serializzazione e presentazione -----
    def serialize_state(self, state: S) -> dict:
        """Rappresentazione JSON-serializzabile dello stato (per la persistenza)."""
        raise NotImplementedError

    def deserialize_state(self, data: dict) -> S:
        """Ricostruisce lo stato da una rappresentazione serializzata."""
        raise NotImplementedError

    def render_text(self, state: S) -> str:
        """Rappresentazione testuale dello stato (utile per log e prompt IA)."""
        raise NotImplementedError

    def describe_move(self, state: S, move: M) -> str:
        """Notazione testuale di una mossa, per il log della partita."""
        return str(move)

    def move_id(self, move: M) -> str:
        """Identificatore stringa di una mossa, usato dal client per selezionarla."""
        return str(move)

    def view_board(self, state: S) -> list:
        """Board come lista di simboli (o None) per il rendering nel frontend.

        Default: usa ``serialize_state`` mappando 0->'X', 1->'O' (Tris, Forza 4).
        """
        symbols = {0: "X", 1: "O", None: None}
        return [symbols.get(c) for c in self.serialize_state(state)["board"]]

    def legal_moves_view(self, state: S) -> list[dict]:
        """Mosse legali in forma strutturata per il frontend (usata dai giochi a
        selezione origine/destinazione, es. dama/scacchi). Default: solo l'id."""
        return [{"id": self.move_id(m)} for m in self.legal_moves(state)]

    def board_changes(self, state: S, move: M) -> list:
        """Celle modificate da una mossa: lista di [indice, nuovo_simbolo|None].

        Generica: confronta la board prima/dopo la mossa. Gestisce così arrocco,
        en passant, promozione e catture senza logica dedicata nel frontend.
        """
        before = self.view_board(state)
        after = self.view_board(self.apply(state, move))
        return [[i, after[i]] for i in range(len(before)) if before[i] != after[i]]

    # ----- Aperture (per i giochi che ne hanno, es. scacchi) -----
    def is_repetition_draw(self, history: list[str]) -> bool:
        """Patta per ripetizione dichiarata dalle regole del gioco (default: mai)."""
        return False

    def opening_move(self, state: S, history: list[str], prefer: list[str] | None = None):
        """Mossa da 'libro' se la posizione segue una linea nota; altrimenti None."""
        return None

    def opening_name(self, history: list[str]) -> str | None:
        """Nome dell'apertura riconosciuta dalla sequenza di mosse; altrimenti None."""
        return None

    def heuristic(self, state: S, player: Player) -> float:
        """Valutazione euristica dello stato dal punto di vista di ``player``.

        Usata dall'IA locale quando la ricerca è limitata in profondità
        (``search_depth`` non None). Default neutro.
        """
        return 0.0

    # ----- Nodi del caso (giochi stocastici, es. backgammon) -----
    # Il flusso è: quando ``is_chance_node`` è vero non ci sono mosse legali; chi
    # orchestra la partita (il backend) estrae un evento secondo ``chance_outcomes``
    # e lo applica con ``apply_chance``. Le mosse dei giocatori restano deterministiche.
    def is_chance_node(self, state: S) -> bool:
        """True se l'evoluzione dipende da un evento aleatorio (es. lancio di dadi)."""
        return False

    def chance_outcomes(self, state: S) -> Sequence[tuple[object, float]]:
        """Coppie (evento, probabilità) per un nodo del caso; vuoto altrimenti."""
        return []

    def apply_chance(self, state: S, event) -> S:
        """Applica un evento aleatorio (es. un tiro di dadi) a un nodo del caso."""
        raise NotImplementedError

    def describe_chance(self, event) -> str:
        """Notazione testuale di un evento aleatorio, per il log della partita."""
        return str(event)

    # ----- Informazioni accessorie per il client -----
    def view_status(self, state: S) -> str | None:
        """Riga di stato informativa da mostrare in partita (es. i dadi del turno)."""
        return None
