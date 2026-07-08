"""Client HTTP verso il backend FastAPI.

Tutte le operazioni sui dati passano da qui: il frontend non accede al database.
"""

from __future__ import annotations

import httpx
from django.conf import settings
from django.utils.translation import get_language

BASE = settings.BACKEND_API_URL.rstrip("/")
TIMEOUT = 10.0


class ApiError(Exception):
    """Errore restituito dal backend o di connessione."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _request(method: str, path: str, **kwargs):
    # i18n: il backend risponde nella lingua scelta dall'utente (Accept-Language).
    headers = kwargs.pop("headers", {}) or {}
    headers.setdefault("Accept-Language", get_language() or "it")
    try:
        with httpx.Client(base_url=BASE, timeout=TIMEOUT) as client:
            response = client.request(method, path, headers=headers, **kwargs)
    except httpx.RequestError as exc:
        raise ApiError(f"Impossibile contattare il backend ({BASE}). È avviato?") from exc

    if response.status_code >= 400:
        detail: object = f"Errore {response.status_code}"
        try:
            body = response.json()
            detail = body.get("detail", detail)
        except ValueError:
            detail = response.text or detail
        if isinstance(detail, list):  # errori di validazione di FastAPI/Pydantic
            detail = "; ".join(str(d.get("msg", d)) for d in detail)
        raise ApiError(str(detail), status=response.status_code)

    if response.status_code == 204 or not response.content:
        return None
    return response.json()


# ----- Giochi -----
def list_games():
    return _request("GET", "/games")


def get_tilt(user_id):
    return _request("GET", f"/users/{user_id}/tilt")


def explain_move(session_id, ply: int):
    return _request("POST", f"/sessions/{session_id}/explain", json={"ply": ply})


# ----- Arena IA (classifica dei concorrenti e tornei) -----
def arena_identities():
    return _request("GET", "/arena/identities")


def arena_ranking(game_code):
    return _request("GET", f"/arena/ranking/{game_code}")


def arena_tournaments():
    return _request("GET", "/arena/tournaments")


def arena_tournament(tournament_id):
    return _request("GET", f"/arena/tournaments/{tournament_id}")


def create_tournament(data: dict):
    return _request("POST", "/arena/tournaments", json=data)


# ----- Utenti -----
def list_users():
    return _request("GET", "/users")


def get_user(user_id):
    return _request("GET", f"/users/{user_id}")


def get_user_history(user_id):
    return _request("GET", f"/users/{user_id}/history")


def get_chess_profile(user_id):
    return _request("GET", f"/users/{user_id}/chess-profile")


def analyze_user_history(user_id):
    """Accoda l'analisi motore delle partite non ancora analizzate (stima blunder)."""
    return _request("POST", f"/users/{user_id}/analyze-history")


def update_user_prefs(user_id, values: dict):
    return _request("PUT", f"/users/{user_id}/prefs", json=values)


def create_user(data: dict):
    return _request("POST", "/users", json=data)


# ----- Autenticazione giocatori e approvazione delle registrazioni -----
def login(identifier: str, password: str):
    """Login sul backend: restituisce token di sessione, scadenza e dati utente."""
    return _request("POST", "/auth/login", json={"identifier": identifier, "password": password})


def logout(token: str):
    return _request("POST", "/auth/logout", headers={"X-Auth-Token": token})


def auth_me(token: str):
    return _request("GET", "/auth/me", headers={"X-Auth-Token": token})


def approve_user(user_id, token: str):
    """Accetta una richiesta di registrazione: riservato al super admin."""
    return _request("POST", f"/users/{user_id}/approve", headers={"X-Admin-Token": token})


def reject_user(user_id, token: str):
    """Respinge (elimina) una richiesta in attesa: riservato al super admin."""
    return _request("DELETE", f"/users/{user_id}", headers={"X-Admin-Token": token})


# ----- Community: presenza online e partite del giocatore -----
def heartbeat(token: str):
    """Rinnova la presenza online del giocatore autenticato."""
    return _request("POST", "/auth/heartbeat", headers={"X-Auth-Token": token})


def community_online():
    """Giocatori online adesso, con il punteggio complessivo (badge)."""
    return _request("GET", "/community/online")


def my_games(token: str):
    """Partite in corso del giocatore autenticato (sfide ricevute comprese)."""
    return _request("GET", "/community/my-games", headers={"X-Auth-Token": token})


# ----- Gruppi -----
def list_groups():
    return _request("GET", "/groups")


def list_proposals():
    return _request("GET", "/groups/proposals")


def create_proposal(data: dict):
    return _request("POST", "/groups/proposals", json=data)


def vote_proposal(proposal_id, data: dict):
    return _request("POST", f"/groups/proposals/{proposal_id}/vote", json=data)


# ----- Partite -----
def record_match(data: dict):
    return _request("POST", "/matches", json=data)


# ----- Sessioni di gioco -----
def create_session(data: dict):
    return _request("POST", "/sessions", json=data)


def get_session(session_id):
    return _request("GET", f"/sessions/{session_id}")


def session_move(session_id, data: dict, token: str | None = None):
    """Invia una mossa; nelle partite a distanza serve il token del giocatore."""
    headers = {"X-Auth-Token": token} if token else {}
    return _request("POST", f"/sessions/{session_id}/move", json=data, headers=headers)


def session_replay(session_id):
    """Moviola: tutte le posizioni della partita (per rewind e step-by-step)."""
    return _request("GET", f"/sessions/{session_id}/replay")


def session_note(session_id, ply: int, text: str, token: str | None = None):
    headers = {"X-Auth-Token": token} if token else {}
    return _request(
        "POST", f"/sessions/{session_id}/note", json={"ply": ply, "text": text}, headers=headers
    )


def start_analysis(session_id):
    return _request("POST", f"/sessions/{session_id}/analysis")


def get_analysis(session_id):
    return _request("GET", f"/sessions/{session_id}/analysis")


def start_sparring(level: str, games: int, engine_ms: int, token: str):
    return _request(
        "POST",
        "/admin/sparring",
        json={"level": level, "games": games, "engine_ms": engine_ms},
        headers={"X-Admin-Token": token},
    )


def sparring_state():
    return _request("GET", "/admin/sparring")


def session_hint(session_id, token: str | None = None):
    headers = {"X-Auth-Token": token} if token else {}
    return _request("POST", f"/sessions/{session_id}/hint", headers=headers)


def session_resign(session_id, side: str, token: str | None = None):
    headers = {"X-Auth-Token": token} if token else {}
    return _request("POST", f"/sessions/{session_id}/resign", json={"side": side}, headers=headers)


def session_draw(session_id, side: str, action: str, token: str | None = None):
    headers = {"X-Auth-Token": token} if token else {}
    return _request(
        "POST",
        f"/sessions/{session_id}/draw",
        json={"side": side, "action": action},
        headers=headers,
    )


def run_batch(data: dict):
    return _request("POST", "/sessions/batch", json=data)


# ----- Tutorial (istruzione guidata) -----
def list_lessons(token: str | None = None):
    """Indice delle lezioni; col token include i progressi personali."""
    headers = {"X-Auth-Token": token} if token else {}
    return _request("GET", "/lessons", headers=headers)


def get_lesson(code: str, token: str | None = None):
    headers = {"X-Auth-Token": token} if token else {}
    return _request("GET", f"/lessons/{code}", headers=headers)


def save_lesson_progress(code: str, step: int, completed: bool, token: str):
    return _request(
        "POST",
        f"/lessons/{code}/progress",
        json={"step": step, "completed": completed},
        headers={"X-Auth-Token": token},
    )


# ----- Configurazione / super admin -----
def tts_status():
    """Stato della voce sintetica: motori e voci per lingua, cache."""
    return _request("GET", "/tts/status")


def get_config():
    return _request("GET", "/config")


def get_settings():
    return _request("GET", "/admin/settings")


def update_settings(values: dict, token: str):
    return _request(
        "PUT", "/admin/settings", json={"values": values}, headers={"X-Admin-Token": token}
    )


def get_ai_providers():
    return _request("GET", "/admin/ai-providers")


def update_ai_providers(active: str, providers: dict, token: str):
    return _request(
        "PUT",
        "/admin/ai-providers",
        json={"active": active, "providers": providers},
        headers={"X-Admin-Token": token},
    )


def test_ai_provider(code: str, token: str):
    return _request("POST", f"/admin/ai-providers/{code}/test", headers={"X-Admin-Token": token})


def test_stockfish(token: str):
    return _request("POST", "/admin/stockfish/test", headers={"X-Admin-Token": token})


# ----- Classifiche -----
def universal_ranking():
    return _request("GET", "/rankings/universal")


def game_ranking(game_code, scope="global", country=None, region=None):
    params = {"scope": scope}
    if country:
        params["country"] = country
    if region:
        params["region"] = region
    return _request("GET", f"/rankings/games/{game_code}", params=params)
