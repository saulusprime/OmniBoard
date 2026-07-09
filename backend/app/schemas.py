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
    # False = richiesta di registrazione in attesa del super admin (login negato).
    is_approved: bool = False
    # Punteggio complessivo su tutti i giochi (badge di gamification).
    universal_points: float = 0
    # Preferenze estetiche del giocatore (proprietà ``User.prefs``): tema scacchiera,
    # segno del Tris, … — vedi user_prefs.py.
    prefs: dict = {}
    created_at: datetime


class UserPrefsUpdate(BaseModel):
    """Aggiornamento (parziale) delle preferenze estetiche del giocatore."""

    board_theme: Optional[str] = None  # chiave di user_prefs.BOARD_THEMES
    tris_mark: Optional[str] = None  # elemento di user_prefs.TRIS_MARKS ("" = default)


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


# ----- Autenticazione giocatori -----
class LoginRequest(BaseModel):
    """Credenziali di accesso: ci si identifica con l'alias oppure con l'email."""

    identifier: str  # alias o email
    password: str


class LoginOut(BaseModel):
    """Esito del login: token di sessione opaco da presentare come X-Auth-Token."""

    token: str
    expires_at: datetime
    user: UserOut


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


class InviteCreate(BaseModel):
    user_id: int


class InviteRespond(BaseModel):
    accept: bool = True


class InviteOut(BaseModel):
    id: int
    group_id: int
    group_name: str
    user_id: int
    alias: str
    invited_by_alias: str
    status: str
    created_at: Optional[datetime] = None


class RoleChange(BaseModel):
    role: str  # admin | member


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
    # Solo per type="ai": CONCORRENTE scelto per questo lato («gioca contro Claude»,
    # «gioca contro Gemini», codice del catalogo ai_providers). None = provider
    # attivo globale. Validato alla creazione sessione.
    provider: Optional[str] = None

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
    # Partita A DISTANZA: i giocatori usano client diversi e ogni mossa umana
    # richiede l'X-Auth-Token del giocatore al tratto. False = hotseat storico.
    remote: bool = False
    # Orologio di gioco (solo scacchi, opzionale). Categoria: "blitz" (<15′ a testa),
    # "rapid" (15-60′), "classical" (>60′), "fide" (90′ + 30″/mossa, +30′ dopo la 40ª
    # mossa: parametri fissi). time_base_min = minuti a testa (non per fide);
    # time_inc_s = incremento Fischer in secondi/mossa (solo blitz/rapid/classical).
    # Validazione in gameplay.build_time_control.
    time_category: Optional[str] = None
    time_base_min: Optional[int] = None
    time_inc_s: int = 0
    # Posizione iniziale personalizzata (FEN, solo scacchi): la partita parte da
    # qui invece che dalla posizione standard. Validata alla creazione sessione.
    start_fen: Optional[str] = None


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


class SparringIn(BaseModel):
    """Match di sparring: motore interno vs Stockfish (per la stima dell'Elo)."""

    level: str = "hermes"  # preset con Elo simulato noto (atena…pan)
    games: int = 4
    engine_ms: int = 300  # budget del motore interno per mossa


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
