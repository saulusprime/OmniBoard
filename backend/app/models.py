"""Modelli SQLAlchemy: anagrafica, giochi, punteggi, gruppi e fondazione gruppi."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """Anagrafica giocatore."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    first_name = Column(String, nullable=False)  # nome
    last_name = Column(String, nullable=False)  # cognome
    alias = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    nationality = Column(String, nullable=True)  # paese (per classifica nazionale)
    region = Column(String, nullable=True)  # regione (per classifica regionale)
    password_hash = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    scores = relationship("Score", back_populates="user", cascade="all, delete-orphan")
    memberships = relationship(
        "GroupMembership", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def universal_points(self) -> float:
        """Punteggio universale = somma dei punti su tutti i giochi (gamification)."""
        return sum(s.points for s in self.scores)


class Game(Base):
    """Catalogo dei tipi di gioco."""

    __tablename__ = "games"

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    is_stochastic = Column(Boolean, default=False)  # True per giochi con nodi del caso

    scores = relationship("Score", back_populates="game", cascade="all, delete-orphan")


class Score(Base):
    """Punteggio di un utente in un gioco, accumulato giocando partite."""

    __tablename__ = "scores"
    __table_args__ = (UniqueConstraint("user_id", "game_id", name="uq_user_game"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    points = Column(Float, default=0.0, nullable=False)
    matches_played = Column(Integer, default=0, nullable=False)
    wins = Column(Integer, default=0, nullable=False)
    draws = Column(Integer, default=0, nullable=False)
    losses = Column(Integer, default=0, nullable=False)

    user = relationship("User", back_populates="scores")
    game = relationship("Game", back_populates="scores")


class GroupProposal(Base):
    """Proposta di fondazione di un gruppo: si fonda al raggiungimento dei voti."""

    __tablename__ = "group_proposals"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    proposed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="pending")  # pending | founded
    threshold = Column(Integer, default=2)  # voti a favore necessari
    created_at = Column(DateTime, default=utcnow)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)

    votes = relationship(
        "GroupProposalVote", back_populates="proposal", cascade="all, delete-orphan"
    )

    @property
    def favor_count(self) -> int:
        return sum(1 for v in self.votes if v.in_favor)


class GroupProposalVote(Base):
    """Voto di un utente a favore (o contro) la fondazione di un gruppo."""

    __tablename__ = "group_proposal_votes"
    __table_args__ = (UniqueConstraint("proposal_id", "user_id", name="uq_proposal_user"),)

    id = Column(Integer, primary_key=True)
    proposal_id = Column(Integer, ForeignKey("group_proposals.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    in_favor = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    proposal = relationship("GroupProposal", back_populates="votes")


class Group(Base):
    """Gruppo di giocatori (fondato tramite una proposta votata)."""

    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    memberships = relationship(
        "GroupMembership", back_populates="group", cascade="all, delete-orphan"
    )


class GroupMembership(Base):
    """Appartenenza di un utente a un gruppo."""

    __tablename__ = "group_memberships"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_user"),)

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String, default="member")  # founder | member
    joined_at = Column(DateTime, default=utcnow)

    group = relationship("Group", back_populates="memberships")
    user = relationship("User", back_populates="memberships")


class GameSession(Base):
    """Partita giocabile con stato persistito.

    Ogni lato è di uno di tre tipi: **umano** (``*_is_ai`` False), **IA via API**
    (``*_is_ai`` True, ``*_ai_kind`` = "ai") o **Stockfish** (``*_ai_kind`` =
    "stockfish"). ``*_ai_kind`` è None per gli umani; per righe storiche con
    ``*_is_ai`` True e kind assente si assume "ai".
    """

    __tablename__ = "game_sessions"

    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    x_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # None se IA
    o_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # None se IA
    x_is_ai = Column(Boolean, default=False, nullable=False)
    o_is_ai = Column(Boolean, default=False, nullable=False)
    x_ai_kind = Column(String(16), nullable=True)  # "ai" | "stockfish" (None se umano)
    o_ai_kind = Column(String(16), nullable=True)
    # Livello preconfigurato per il lato Stockfish (chiave di stockfish.PRESETS, es.
    # "zeus"); None = parametri globali del super admin.
    x_ai_level = Column(String(16), nullable=True)
    o_ai_level = Column(String(16), nullable=True)
    state_json = Column(String, nullable=False)  # stato serializzato dal motore
    moves_json = Column(String, default="[]", nullable=False)  # log delle mosse
    status = Column(String, default="in_progress", nullable=False)  # in_progress | finished
    winner = Column(String, nullable=True)  # x | o | draw
    last_ai_cell = Column(Integer, nullable=True)
    last_ai_source = Column(String, nullable=True)  # book | stockfish | <provider> | engine | local
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    game = relationship("Game")
    x_user = relationship("User", foreign_keys=[x_user_id])
    o_user = relationship("User", foreign_keys=[o_user_id])


class Setting(Base):
    """Parametro di configurazione del programma, gestibile dal super admin."""

    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)  # valore serializzato come testo
    value_type = Column(String, nullable=False)  # int | float | bool | str
    category = Column(String, nullable=False)
    label = Column(String, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class AiProvider(Base):
    """Credenziali e configurazione di un provider IA (Qwen, Claude, OpenAI, …)."""

    __tablename__ = "ai_providers"

    code = Column(String, primary_key=True)  # qwen | anthropic | openai
    label = Column(String, nullable=False)
    kind = Column(String, nullable=False)  # "openai" (compatibile) | "anthropic"
    base_url = Column(String, nullable=True)
    model = Column(String, nullable=True)
    api_key = Column(String, nullable=True)  # token; non esposto in lettura dall'API
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
