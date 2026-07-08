"""i18n del backend: le risposte seguono l'``Accept-Language`` della richiesta.

L'italiano è la LINGUA SORGENTE (le stringhe nel codice restano italiane, come
tutto il progetto); l'inglese arriva da un **catalogo a dizionario**
(``catalog_en.py``). Per una sola lingua di destinazione il dizionario batte
gettext/babel: niente estrazione/compilazione, tutto greppabile, il fallback è
la stringa sorgente. Se le lingue cresceranno, questo modulo è l'unico punto da
evolvere (stessa interfaccia ``_()``).

Flusso: il middleware (registrato in ``main.py``) legge ``Accept-Language`` e
imposta la lingua in una **ContextVar** (sicura con richieste concorrenti e
thread del worker no — i worker IA girano fuori richiesta e restano in
italiano: producono DATI PERSISTITI, mai testi di risposta). ``_(testo)``
traduce al momento della RISPOSTA: ciò che è salvato nel DB resta italiano e la
stessa risorsa può essere servita in lingue diverse a client diversi.

Il frontend Django inoltra la lingua scelta dall'utente su ogni chiamata
(``api_client``); i client API diretti usano l'header standard.
"""

from __future__ import annotations

from contextvars import ContextVar

from .catalog_en import CATALOG_EN

SUPPORTED = ("it", "en")
_lang: ContextVar[str] = ContextVar("lang", default="it")


def parse_accept_language(header: str | None) -> str:
    """La migliore lingua supportata dall'header (default: italiano)."""
    if not header:
        return "it"
    for part in header.split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in SUPPORTED:
            return code
    return "it"


def set_language(lang: str):
    """Imposta la lingua della richiesta corrente; ritorna il token per il reset."""
    return _lang.set(lang if lang in SUPPORTED else "it")


def reset_language(token) -> None:
    _lang.reset(token)


def get_language() -> str:
    return _lang.get()


def _(text: str) -> str:
    """Traduce ``text`` nella lingua della richiesta (fallback: la sorgente)."""
    if _lang.get() == "it" or not text:
        return text
    return CATALOG_EN.get(text, text)
