"""Cifratura dei token dei provider IA a riposo nel DB (Fernet).

I token API non stanno più in chiaro nella tabella ``ai_providers``: si salvano
come ``enc:<fernet>`` (AES-128-CBC + HMAC-SHA256, libreria ``cryptography``) e si
decifrano solo al momento di usarli. Nessun cambio di schema: stessa colonna,
prefisso riconoscibile; le righe ancora in chiaro vengono cifrate al primo avvio
(``encrypt_legacy_rows`` chiamata dal seed).

**Chiave**: ``TOKENS_KEY`` in ``.env`` (32 byte urlsafe-base64, generabile con
``Fernet.generate_key()``). Se assente si DERIVA da ``ADMIN_TOKEN`` (PBKDF2, sale
fisso dell'applicazione): zero configurazione in sviluppo, ma cambiare
ADMIN_TOKEN senza aver fissato TOKENS_KEY rende i token illeggibili — in quel
caso la pagina Provider IA mostra il token da reinserire. In produzione fissare
TOKENS_KEY è la scelta giusta.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

PREFIX = "enc:"
_SALT = b"scacchi-ai-provider-tokens-v1"  # sale applicativo per la chiave derivata


def _key() -> bytes:
    explicit = (os.getenv("TOKENS_KEY") or "").strip()
    if explicit:
        return explicit.encode()
    admin = os.getenv("ADMIN_TOKEN") or ""
    derived = hashlib.pbkdf2_hmac("sha256", admin.encode(), _SALT, 200_000)
    return base64.urlsafe_b64encode(derived)


def _fernet() -> Fernet:
    return Fernet(_key())


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def encrypt(plain: str) -> str:
    """Token in chiaro → forma cifrata da salvare (``enc:…``)."""
    return PREFIX + _fernet().encrypt(plain.encode()).decode()


def decrypt(stored: str | None) -> str | None:
    """Forma salvata → token in chiaro; None se il valore non è decifrabile.

    Un valore senza prefisso è un token legacy in chiaro e passa com'è (verrà
    cifrato al prossimo avvio dal seed). ``None``/vuoto → None.
    """
    if not stored:
        return None
    if not stored.startswith(PREFIX):
        return stored
    try:
        return _fernet().decrypt(stored[len(PREFIX) :].encode()).decode()
    except (InvalidToken, ValueError):
        return None  # chiave cambiata o dato corrotto: come non avere il token
