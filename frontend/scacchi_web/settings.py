"""Impostazioni Django del frontend Scacchi.

Il frontend è puramente presentazione: NON possiede dati di dominio (li legge dal
backend FastAPI). Per questo sono disattivate le app che richiedono un database
(auth, sessioni, admin): i messaggi usano lo storage su cookie.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Carica le variabili dal file .env nella root del progetto, se presente.
load_dotenv(BASE_DIR.parent / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if h.strip()
]

# URL del backend FastAPI usato dal frontend per tutte le operazioni sui dati.
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000")

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "django.contrib.messages",
    "web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Sessione su COOKIE FIRMATO: il frontend resta senza database proprio (nessuna
# tabella di sessione). Nel cookie vivono solo il token di sessione rilasciato
# dal backend al login e i dati minimi del giocatore (id e alias).
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_HTTPONLY = True

ROOT_URLCONF = "scacchi_web.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                # Espone il giocatore loggato (auth_user) a tutti i template.
                "web.context_processors.auth_user",
            ],
        },
    },
]

WSGI_APPLICATION = "scacchi_web.wsgi.application"
ASGI_APPLICATION = "scacchi_web.asgi.application"

# Database di riserva (non usato dalla logica: il dominio vive nel backend).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "frontend_dummy.sqlite3",
    }
}

# Messaggi su cookie: niente dipendenza dalle sessioni/DB.
MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"

STATIC_URL = "static/"

LANGUAGE_CODE = "it"
TIME_ZONE = "Europe/Rome"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
