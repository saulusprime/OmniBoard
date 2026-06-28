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


# ----- Classifiche -----
class RankingEntry(BaseModel):
    rank: int
    user_id: int
    alias: str
    full_name: str
    nationality: Optional[str] = None
    region: Optional[str] = None
    points: float
