"""Modello astratto di un gioco a turni per due giocatori.

Definisce l'interfaccia che ogni gioco concreto (scacchi, dama, tris, forza 4)
implementerà. È previsto un *hook* per i nodi del caso (dadi), non ancora usato,
così da poter aggiungere in futuro giochi stocastici come il backgammon.

Questo è lo scheletro del motore: le implementazioni dei singoli giochi verranno
aggiunte in moduli dedicati (es. ``engine/games/tictactoe.py``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, Optional, Sequence, TypeVar

Player = int  # due giocatori: 0 e 1

S = TypeVar("S")  # tipo dello stato di gioco
M = TypeVar("M")  # tipo della mossa


@dataclass(frozen=True)
class Outcome:
    """Esito di una partita terminata. ``winner`` None indica una patta."""

    winner: Optional[Player]


class Game(ABC, Generic[S, M]):
    """Interfaccia astratta di un gioco a turni a informazione perfetta.

    Lo stato è trattato come immutabile: ``apply`` restituisce un nuovo stato.
    """

    code: str = ""
    name: str = ""
    is_stochastic: bool = False

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

    # ----- Hook per i nodi del caso (estensione futura) -----
    def is_chance_node(self, state: S) -> bool:
        """True se l'evoluzione dipende da un evento aleatorio (es. lancio di dadi)."""
        return False

    def chance_outcomes(self, state: S) -> Sequence[tuple[object, float]]:
        """Coppie (evento, probabilità) per un nodo del caso; vuoto altrimenti."""
        return []
