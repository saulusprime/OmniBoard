"""Client HTTP verso il backend FastAPI.

Tutte le operazioni sui dati passano da qui: il frontend non accede al database.
"""

from __future__ import annotations

import httpx
from django.conf import settings

BASE = settings.BACKEND_API_URL.rstrip("/")
TIMEOUT = 10.0


class ApiError(Exception):
    """Errore restituito dal backend o di connessione."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _request(method: str, path: str, **kwargs):
    try:
        with httpx.Client(base_url=BASE, timeout=TIMEOUT) as client:
            response = client.request(method, path, **kwargs)
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


# ----- Utenti -----
def list_users():
    return _request("GET", "/users")


def get_user(user_id):
    return _request("GET", f"/users/{user_id}")


def get_user_history(user_id):
    return _request("GET", f"/users/{user_id}/history")


def get_chess_profile(user_id):
    return _request("GET", f"/users/{user_id}/chess-profile")


def update_user_prefs(user_id, values: dict):
    return _request("PUT", f"/users/{user_id}/prefs", json=values)


def create_user(data: dict):
    return _request("POST", "/users", json=data)


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


def session_move(session_id, data: dict):
    return _request("POST", f"/sessions/{session_id}/move", json=data)


def run_batch(data: dict):
    return _request("POST", "/sessions/batch", json=data)


# ----- Configurazione / super admin -----
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
