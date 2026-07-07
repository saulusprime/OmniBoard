"""Modelli SQLAlchemy: anagrafica, giochi, punteggi, gruppi e fondazione gruppi."""

from __future__ import annotations

import json
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
    # La registrazione è una RICHIESTA: solo il super admin la accetta. Finché
    # is_approved è False il giocatore non può autenticarsi (login negato).
    is_approved = Column(Boolean, default=False, nullable=False)
    # Presenza online (community): aggiornata dal login e dall'heartbeat del client.
    # "Online" = visto negli ultimi community.online_window_s secondi.
    last_seen_at = Column(DateTime, nullable=True)
    # Preferenze estetiche del giocatore (JSON: tema scacchiera, segno del Tris, …).
    # Registro e validazione in user_prefs.py; esposte come proprietà ``prefs``.
    prefs_json = Column(String, default="{}", nullable=False)
    created_at = Column(DateTime, default=utcnow)

    @property
    def prefs(self) -> dict:
        """Preferenze parse-ate (usata anche dagli schemi Pydantic via from_attributes)."""
        try:
            return json.loads(self.prefs_json or "{}")
        except (TypeError, ValueError):
            return {}

    scores = relationship("Score", back_populates="user", cascade="all, delete-orphan")
    memberships = relationship(
        "GroupMembership", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def universal_points(self) -> float:
        """Punteggio universale = somma dei punti su tutti i giochi (gamification)."""
        return sum(s.points for s in self.scores)


class AuthSession(Base):
    """Sessione di autenticazione di un giocatore (login/logout).

    Il token è una stringa opaca casuale consegnata al client dopo il login;
    il server la ritrova qui per riconoscere il giocatore (``GET /auth/me``).
    Il logout cancella la riga; le sessioni scadute vengono ripulite pigramente
    al primo uso. Le password NON vivono qui: in anagrafica c'è solo l'hash
    (``User.password_hash``, PBKDF2 — vedi security.py).
    """

    __tablename__ = "auth_sessions"

    id = Column(Integer, primary_key=True)
    token = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=False)

    user = relationship("User")


class LessonProgress(Base):
    """Progresso di un giocatore in una lezione del tutorial (istruzione guidata).

    Una riga per (utente, lezione): ``last_step`` è l'ultimo passo raggiunto
    (0-based, per riprendere da dove si era rimasti), ``completed`` scatta
    quando l'allievo supera l'ultimo passo. Il contenuto delle lezioni NON
    vive nel DB (è codice: ``app/lessons/``), qui solo lo stato personale.
    """

    __tablename__ = "lesson_progress"
    __table_args__ = (UniqueConstraint("user_id", "lesson_code"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    lesson_code = Column(String, nullable=False, index=True)
    last_step = Column(Integer, nullable=False, default=0)
    completed = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("User")


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
    # Partita A DISTANZA: i due giocatori usano client diversi; ogni mossa umana
    # richiede il token di sessione (X-Auth-Token) del giocatore al tratto.
    # False = hotseat sullo stesso schermo (comportamento storico, nessun token).
    remote = Column(Boolean, nullable=False, default=False, server_default="0")
    # Concorrenti IA multipli: per i lati di tipo "ai", il provider SCELTO alla
    # creazione («gioca contro Claude/Gemini/Grok/…», codice del catalogo
    # ai_providers). None = si usa il provider attivo globale (storico).
    x_ai_provider = Column(String, nullable=True)
    o_ai_provider = Column(String, nullable=True)
    # Patta d'accordo (FIDE 9.1): lato («x»/«o») con un'offerta di patta PENDENTE;
    # None = nessuna offerta. L'offerta decade se l'altro giocatore muove.
    draw_offer = Column(String, nullable=True)
    # Analisi post-partita (Stockfish): JSON con le valutazioni mossa per mossa
    # e gli errori marcati — calcolata una volta e riletta da qui (vedi analysis.py).
    analysis_json = Column(String, nullable=True)
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
    # Orologio di gioco (solo scacchi, opzionale). Categoria: blitz | rapid |
    # classical | fide (None = senza orologio); tempo base e incremento in secondi;
    # tempi residui dei due lati in MILLISECONDI; istante d'inizio del turno corrente
    # (l'orologio del giocatore al tratto scorre da qui). La logica è in gameplay.py.
    tc_category = Column(String(16), nullable=True)
    tc_base_s = Column(Integer, nullable=True)
    tc_inc_s = Column(Integer, nullable=True)
    x_clock_ms = Column(Integer, nullable=True)
    o_clock_ms = Column(Integer, nullable=True)
    turn_started_at = Column(DateTime, nullable=True)
    finish_reason = Column(String(16), nullable=True)  # "time" = decisa dall'orologio
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
