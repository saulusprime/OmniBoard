"""Schemi Pydantic (v2) per input/output dell'API."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ----- Utenti -----
class UserCreate(BaseModel):
    first_name: str
    last_name: str
    alias: str
    email: str
    nationality: Optional[str] = None
    region: Optional[str] = None
    password: Optional[str] = None

    @field_validator("first_name", "last_name", "alias")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Campo obbligatorio")
        return v.strip()

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError("Email non valida")
        return v


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    first_name: str
    last_name: str
    alias: str
    email: str
    nationality: Optional[str] = None
    region: Optional[str] = None
    created_at: datetime


class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    game_code: str
    game_name: str
    points: float
    matches_played: int
    wins: int
    draws: int
    losses: int


class UserDetail(UserOut):
    universal_points: float
    scores: list[ScoreOut] = []


# ----- Giochi -----
class GameOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    is_stochastic: bool
    playable: bool = False


# ----- Gruppi e fondazione -----
class GroupProposalCreate(BaseModel):
    name: str
    proposed_by: int
    threshold: int = 2

    @field_validator("name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Nome obbligatorio")
        return v.strip()


class VoteCreate(BaseModel):
    user_id: int
    in_favor: bool = True


class ProposalOut(BaseModel):
    id: int
    name: str
    proposed_by: int
    status: str
    threshold: int
    favor_count: int
    group_id: Optional[int] = None
    created_at: datetime


class MembershipOut(BaseModel):
    user_id: int
    alias: str
    role: str


class GroupOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    members: list[MembershipOut] = []


# ----- Partite e punteggi -----
class MatchResult(BaseModel):
    game_code: str
    player_a: int
    player_b: int
    result: str  # "a" | "b" | "draw"

    @field_validator("result")
    @classmethod
    def valid_result(cls, v: str) -> str:
        if v not in {"a", "b", "draw"}:
            raise ValueError("result deve essere 'a', 'b' o 'draw'")
        return v


# ----- Sessioni di gioco -----
class PlayerSpec(BaseModel):
    # Tipo di giocatore: "human" (umano), "ai" (IA via API: Qwen/Claude/…) oppure
    # "stockfish" (motore Stockfish configurabile). Vedi backend/app/opponents/.
    type: str
    user_id: Optional[int] = None
    # Solo per type="stockfish": livello preconfigurato (chiave di stockfish.PRESETS,
    # es. "zeus"/"atena"/…); None = parametri globali. Validato alla creazione sessione.
    level: Optional[str] = None

    @field_validator("type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        if v not in {"human", "ai", "stockfish"}:
            raise ValueError("type deve essere 'human', 'ai' o 'stockfish'")
        return v


class SessionCreate(BaseModel):
    game_code: str = "tictactoe"
    x: PlayerSpec
    o: PlayerSpec


class MoveIn(BaseModel):
    move: str  # identificatore della mossa (vedi Game.move_id): cella, colonna o percorso


class BatchCreate(BaseModel):
    """Esegue ``count`` partite consecutive IA-vs-IA e ne restituisce il riepilogo.

    Il limite massimo di ``count`` è il parametro configurabile ``games.batch_max``.
    """

    game_code: str = "tictactoe"
    count: int = 1

    @field_validator("count")
    @classmethod
    def valid_count(cls, v: int) -> int:
        if v < 1:
            raise ValueError("count deve essere >= 1")
        return v


class SettingsUpdate(BaseModel):
    """Aggiornamento di uno o più parametri (valori come stringhe dal form)."""

    values: dict[str, str]


class AiProvidersUpdate(BaseModel):
    """Aggiornamento dei provider IA e del provider attivo.

    ``providers`` mappa il codice provider ai campi {base_url, model, api_key}.
    """

    active: str = ""
    providers: dict[str, dict] = {}


# ----- Classifiche -----
class RankingEntry(BaseModel):
    rank: int
    user_id: int
    alias: str
    full_name: str
    nationality: Optional[str] = None
    region: Optional[str] = None
    points: float
