"""Smoke test del frontend Django.

Verifica che la home risponda anche quando il backend non è raggiungibile
(degrado controllato): il frontend non deve andare in errore 500.
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scacchi_web.settings")
django.setup()

from django.test import Client  # noqa: E402


def test_home_renders_even_if_backend_down():
    # Punta a una porta chiusa per simulare il backend irraggiungibile.
    import web.api_client as api

    api.BASE = "http://127.0.0.1:9"

    # SERVER_NAME="localhost" è in ALLOWED_HOSTS (il test client userebbe "testserver").
    response = Client().get("/", SERVER_NAME="localhost")
    assert response.status_code == 200
    assert b"Scacchi" in response.content
