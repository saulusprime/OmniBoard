"""Modelli SQLAlchemy: anagrafica, giochi, punteggi, gruppi e fondazione gruppi.

Stile tipizzato SQLAlchemy 2.0 (``Mapped[]`` + ``mapped_column``): gli attributi
hanno il tipo Python reale (niente falsi positivi degli analizzatori sugli
attributi ``Column[...]``). La NULLABILITÀ segue l'annotazione (``T | None`` =
nullable) ed è stata mantenuta IDENTICA allo schema storico — comprese le
colonne nullable "per omissione" come i ``created_at`` (verificato con
``alembic check``: nessuna differenza di schema).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """Anagrafica giocatore."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(String)  # nome
    last_name: Mapped[str] = mapped_column(String)  # cognome
    alias: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    nationality: Mapped[str | None] = mapped_column(String)  # paese (classifica nazionale)
    region: Mapped[str | None] = mapped_column(String)  # regione (classifica regionale)
    password_hash: Mapped[str | None] = mapped_column(String)
    # La registrazione è una RICHIESTA: solo il super admin la accetta. Finché
    # is_approved è False il giocatore non può autenticarsi (login negato).
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    # Presenza online (community): aggiornata dal login e dall'heartbeat del client.
    # "Online" = visto negli ultimi community.online_window_s secondi.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Preferenze estetiche del giocatore (JSON: tema scacchiera, segno del Tris, …).
    # Registro e validazione in user_prefs.py; esposte come proprietà ``prefs``.
    prefs_json: Mapped[str] = mapped_column(String, default="{}")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)

    @property
    def prefs(self) -> dict:
        """Preferenze parse-ate (usata anche dagli schemi Pydantic via from_attributes)."""
        try:
            return json.loads(self.prefs_json or "{}")
        except (TypeError, ValueError):
            return {}

    scores: Mapped[list[Score]] = relationship(back_populates="user", cascade="all, delete-orphan")
    memberships: Mapped[list[GroupMembership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    user: Mapped[User] = relationship()


class LessonProgress(Base):
    """Progresso di un giocatore in una lezione del tutorial (istruzione guidata).

    Una riga per (utente, lezione): ``last_step`` è l'ultimo passo raggiunto
    (0-based, per riprendere da dove si era rimasti), ``completed`` scatta
    quando l'allievo supera l'ultimo passo. Il contenuto delle lezioni NON
    vive nel DB (è codice: ``app/lessons/``), qui solo lo stato personale.
    """

    __tablename__ = "lesson_progress"
    __table_args__ = (UniqueConstraint("user_id", "lesson_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    lesson_code: Mapped[str] = mapped_column(String, index=True)
    last_step: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship()


class Game(Base):
    """Catalogo dei tipi di gioco."""

    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    # True per giochi con nodi del caso (nullable per schema storico).
    is_stochastic: Mapped[bool | None] = mapped_column(Boolean, default=False)

    scores: Mapped[list[Score]] = relationship(back_populates="game", cascade="all, delete-orphan")


class Score(Base):
    """Punteggio di un utente in un gioco, accumulato giocando partite."""

    __tablename__ = "scores"
    __table_args__ = (UniqueConstraint("user_id", "game_id", name="uq_user_game"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"))
    points: Mapped[float] = mapped_column(Float, default=0.0)
    matches_played: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship(back_populates="scores")
    game: Mapped[Game] = relationship(back_populates="scores")


class Rating(Base):
    """Rating Elo di un GIOCATORE UMANO in un gioco, per stagione.

    Pool pulito: si aggiorna SOLO sulle partite umano-vs-umano concluse (le
    partite contro le IA non lo toccano — le IA hanno il loro pool nell'arena;
    mescolare i due distorcerebbe entrambi). K adattivo stile FIDE (vedi
    ``rating.py``); ``season`` arriva dal parametro ``elo.season``: cambiarlo
    apre una stagione nuova (le righe vecchie restano come storico).
    """

    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("user_id", "game_id", "season", name="uq_user_game_season"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"))
    season: Mapped[str] = mapped_column(String, default="")
    elo: Mapped[float] = mapped_column(Float, default=1500.0)
    peak_elo: Mapped[float] = mapped_column(Float, default=1500.0)
    games: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship()
    game: Mapped[Game] = relationship()


class AiRating(Base):
    """Rating Elo di un CONCORRENTE IA in un gioco (classifica delle IA).

    L'identità è la configurazione del lato ("motore:novizio", "stockfish:zeus",
    "ai:anthropic", …). Aggiornato SOLO su partite IA-vs-IA concluse (tornei o
    sessioni normali): contro gli umani non c'è un rating da confrontare.
    """

    __tablename__ = "ai_ratings"
    __table_args__ = (UniqueConstraint("game_id", "identity", name="uq_game_identity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"))
    identity: Mapped[str] = mapped_column(String)
    elo: Mapped[float] = mapped_column(Float, default=1500.0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)

    game: Mapped[Game] = relationship()


class Tournament(Base):
    """Torneo IA-vs-IA: girone all'italiana tra concorrenti IA di un gioco."""

    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"))
    name: Mapped[str] = mapped_column(String)
    # Doppio girone = andata e ritorno (colori invertiti); singolo = una partita
    # per coppia (il primo elencato ha X).
    double_round: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="running")  # running | finished
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)

    game: Mapped[Game] = relationship()
    games: Mapped[list[TournamentGame]] = relationship(
        back_populates="tournament", cascade="all, delete-orphan"
    )


class TournamentGame(Base):
    """Una partita di torneo: accoppiamento + (a partita giocata) sessione ed esito."""

    __tablename__ = "tournament_games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(Integer, ForeignKey("tournaments.id"))
    x_identity: Mapped[str] = mapped_column(String)
    o_identity: Mapped[str] = mapped_column(String)
    # Compilati quando la partita viene giocata (le partite sono vere sessioni:
    # storico, moviola, PGN inclusi). result ∈ {x, o, draw}; None = da giocare.
    session_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("game_sessions.id"))
    result: Mapped[str | None] = mapped_column(String)

    tournament: Mapped[Tournament] = relationship(back_populates="games")
    session: Mapped[GameSession | None] = relationship()


class Puzzle(Base):
    """Puzzle: posizione + linea di soluzione verificata, con tema e difficoltà.

    ``solution_json`` è la LINEA COMPLETA in UCI: le mosse del solutore agli
    indici pari, le risposte (forzate) dell'avversario ai dispari. ``source``:
    "manual" (autoriale, dal seed) o "auto" (generato dai blunder delle partite
    analizzate — ``source_session_id``/``source_ply`` puntano al momento esatto).
    """

    __tablename__ = "puzzles"
    __table_args__ = (UniqueConstraint("source_session_id", "source_ply", name="uq_puzzle_origin"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"))
    fen: Mapped[str] = mapped_column(String)
    solution_json: Mapped[str] = mapped_column(String)  # lista UCI (JSON)
    theme: Mapped[str] = mapped_column(String)  # "matto in 1" | "colpo vincente" | …
    difficulty: Mapped[int] = mapped_column(Integer, default=2)  # 1 facile … 5 duro
    source: Mapped[str] = mapped_column(String, default="manual")  # manual | auto
    source_session_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("game_sessions.id"))
    source_ply: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)

    game: Mapped[Game] = relationship()


class PuzzleAttempt(Base):
    """Progresso di un giocatore su un puzzle: risolto sì/no e tentativi."""

    __tablename__ = "puzzle_attempts"
    __table_args__ = (UniqueConstraint("user_id", "puzzle_id", name="uq_user_puzzle"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    puzzle_id: Mapped[int] = mapped_column(Integer, ForeignKey("puzzles.id"))
    solved: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship()
    puzzle: Mapped[Puzzle] = relationship()


class GroupProposal(Base):
    """Proposta di fondazione di un gruppo: si fonda al raggiungimento dei voti."""

    __tablename__ = "group_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    proposed_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    status: Mapped[str | None] = mapped_column(String, default="pending")  # pending | founded
    threshold: Mapped[int | None] = mapped_column(Integer, default=2)  # voti necessari
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)
    group_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("groups.id"))

    votes: Mapped[list[GroupProposalVote]] = relationship(
        back_populates="proposal", cascade="all, delete-orphan"
    )

    @property
    def favor_count(self) -> int:
        return sum(1 for v in self.votes if v.in_favor)


class GroupProposalVote(Base):
    """Voto di un utente a favore (o contro) la fondazione di un gruppo."""

    __tablename__ = "group_proposal_votes"
    __table_args__ = (UniqueConstraint("proposal_id", "user_id", name="uq_proposal_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[int] = mapped_column(Integer, ForeignKey("group_proposals.id"))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    in_favor: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)

    proposal: Mapped[GroupProposal] = relationship(back_populates="votes")


class Group(Base):
    """Gruppo di giocatori (fondato tramite una proposta votata)."""

    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)

    memberships: Mapped[list[GroupMembership]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class GroupMembership(Base):
    """Appartenenza di un utente a un gruppo."""

    __tablename__ = "group_memberships"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id"))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    role: Mapped[str | None] = mapped_column(String, default="member")  # founder | member
    joined_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)

    group: Mapped[Group] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class GroupInvite(Base):
    """Invito a entrare in un gruppo (accettato dall'invitato, mai automatico).

    Un solo invito per (gruppo, utente): un re-invito dopo un rifiuto riporta
    la stessa riga a ``pending`` (niente tempesta di righe).
    """

    __tablename__ = "group_invites"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_invite"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id"))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    invited_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|accepted|declined
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)

    group: Mapped[Group] = relationship()
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    inviter: Mapped[User] = relationship(foreign_keys=[invited_by])


class HumanTournament(Base):
    """Torneo fra GIOCATORI UMANI: eliminazione diretta o girone all'italiana.

    Le partite sono vere ``GameSession`` fra i due iscritti (compaiono in
    «le mie partite» di entrambi, come le sfide a distanza). ``group_id``
    opzionale = torneo riservato ai membri di un gruppo.
    """

    __tablename__ = "human_tournaments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"))
    name: Mapped[str] = mapped_column(String)
    format: Mapped[str] = mapped_column(String)  # knockout | round_robin
    double_round: Mapped[bool] = mapped_column(Boolean, default=False)  # solo girone
    status: Mapped[str] = mapped_column(String, default="open")  # open|running|finished
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    group_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("groups.id"))
    winner_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)

    game: Mapped[Game] = relationship()
    group: Mapped[Group | None] = relationship()
    winner: Mapped[User | None] = relationship(foreign_keys=[winner_user_id])
    players: Mapped[list[HumanTournamentPlayer]] = relationship(
        back_populates="tournament", cascade="all, delete-orphan"
    )
    games: Mapped[list[HumanTournamentGame]] = relationship(
        back_populates="tournament", cascade="all, delete-orphan"
    )


class HumanTournamentPlayer(Base):
    """Iscritto a un torneo umano; il seed si assegna all'avvio (Elo, poi alias)."""

    __tablename__ = "human_tournament_players"
    __table_args__ = (UniqueConstraint("tournament_id", "user_id", name="uq_tournament_player"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(Integer, ForeignKey("human_tournaments.id"))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    seed: Mapped[int | None] = mapped_column(Integer)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)

    tournament: Mapped[HumanTournament] = relationship(back_populates="players")
    user: Mapped[User] = relationship()


class HumanTournamentGame(Base):
    """Una partita di torneo umano: turno + accoppiamento + sessione + esito.

    Nell'eliminazione diretta ``round`` parte da 1 e ``slot`` ordina il
    tabellone; un BYE è una riga senza ``o_user_id`` con ``result="x"`` già
    scritto (nessuna sessione). ``result`` ∈ {x, o, draw}; None = da giocare.
    """

    __tablename__ = "human_tournament_games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(Integer, ForeignKey("human_tournaments.id"))
    round: Mapped[int] = mapped_column(Integer, default=1)
    slot: Mapped[int] = mapped_column(Integer, default=0)
    x_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    o_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    session_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("game_sessions.id"))
    result: Mapped[str | None] = mapped_column(String)

    tournament: Mapped[HumanTournament] = relationship(back_populates="games")
    x_user: Mapped[User] = relationship(foreign_keys=[x_user_id])
    o_user: Mapped[User | None] = relationship(foreign_keys=[o_user_id])
    session: Mapped[GameSession | None] = relationship()


class GameSession(Base):
    """Partita giocabile con stato persistito.

    Ogni lato è di uno di tre tipi: **umano** (``*_is_ai`` False), **IA via API**
    (``*_is_ai`` True, ``*_ai_kind`` = "ai") o **Stockfish** (``*_ai_kind`` =
    "stockfish"). ``*_ai_kind`` è None per gli umani; per righe storiche con
    ``*_is_ai`` True e kind assente si assume "ai".
    """

    __tablename__ = "game_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"))
    # Partita A DISTANZA: i due giocatori usano client diversi; ogni mossa umana
    # richiede il token di sessione (X-Auth-Token) del giocatore al tratto.
    # False = hotseat sullo stesso schermo (comportamento storico, nessun token).
    remote: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # Concorrenti IA multipli: per i lati di tipo "ai", il provider SCELTO alla
    # creazione («gioca contro Claude/Gemini/Grok/…», codice del catalogo
    # ai_providers). None = si usa il provider attivo globale (storico).
    x_ai_provider: Mapped[str | None] = mapped_column(String)
    o_ai_provider: Mapped[str | None] = mapped_column(String)
    # Patta d'accordo (FIDE 9.1): lato («x»/«o») con un'offerta di patta PENDENTE;
    # None = nessuna offerta. L'offerta decade se l'altro giocatore muove.
    draw_offer: Mapped[str | None] = mapped_column(String)
    # Analisi post-partita (Stockfish): JSON con le valutazioni mossa per mossa
    # e gli errori marcati — calcolata una volta e riletta da qui (vedi analysis.py).
    analysis_json: Mapped[str | None] = mapped_column(String)
    x_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))  # None se IA
    o_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))  # None se IA
    x_is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    o_is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    x_ai_kind: Mapped[str | None] = mapped_column(String(16))  # "ai" | "stockfish" (None umano)
    o_ai_kind: Mapped[str | None] = mapped_column(String(16))
    # Livello preconfigurato del lato: preset Stockfish ("zeus", …) o livello del
    # motore locale ("novizio", …); None = parametri globali del super admin.
    x_ai_level: Mapped[str | None] = mapped_column(String(16))
    o_ai_level: Mapped[str | None] = mapped_column(String(16))
    # Orologio di gioco (solo scacchi, opzionale). Categoria: blitz | rapid |
    # classical | fide (None = senza orologio); tempo base e incremento in secondi;
    # tempi residui dei due lati in MILLISECONDI; istante d'inizio del turno corrente
    # (l'orologio del giocatore al tratto scorre da qui). La logica è in gameplay.py.
    tc_category: Mapped[str | None] = mapped_column(String(16))
    tc_base_s: Mapped[int | None] = mapped_column(Integer)
    tc_inc_s: Mapped[int | None] = mapped_column(Integer)
    x_clock_ms: Mapped[int | None] = mapped_column(Integer)
    o_clock_ms: Mapped[int | None] = mapped_column(Integer)
    turn_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finish_reason: Mapped[str | None] = mapped_column(String(16))  # "time" = dall'orologio
    # Posizione iniziale personalizzata (FEN, solo scacchi): la partita non parte
    # dalla posizione standard e ogni replay/analisi riparte da qui. None = standard.
    start_fen: Mapped[str | None] = mapped_column(String)
    state_json: Mapped[str] = mapped_column(String)  # stato serializzato dal motore
    moves_json: Mapped[str] = mapped_column(String, default="[]")  # log delle mosse
    status: Mapped[str] = mapped_column(String, default="in_progress")  # in_progress | finished
    winner: Mapped[str | None] = mapped_column(String)  # x | o | draw
    last_ai_cell: Mapped[int | None] = mapped_column(Integer)
    last_ai_source: Mapped[str | None] = mapped_column(String)  # book | stockfish | <provider> | …
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    game: Mapped[Game] = relationship()
    x_user: Mapped[User | None] = relationship(foreign_keys=[x_user_id])
    o_user: Mapped[User | None] = relationship(foreign_keys=[o_user_id])


class Setting(Base):
    """Parametro di configurazione del programma, gestibile dal super admin."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)  # valore serializzato come testo
    value_type: Mapped[str] = mapped_column(String)  # int | float | bool | str
    category: Mapped[str] = mapped_column(String)
    label: Mapped[str] = mapped_column(String)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AiProvider(Base):
    """Credenziali e configurazione di un provider IA (Qwen, Claude, OpenAI, …)."""

    __tablename__ = "ai_providers"

    code: Mapped[str] = mapped_column(String, primary_key=True)  # qwen | anthropic | openai
    label: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)  # "openai" (compatibile) | "anthropic"
    base_url: Mapped[str | None] = mapped_column(String)
    model: Mapped[str | None] = mapped_column(String)
    api_key: Mapped[str | None] = mapped_column(String)  # token; mai esposto in lettura
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
