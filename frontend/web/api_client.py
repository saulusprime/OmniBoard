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
