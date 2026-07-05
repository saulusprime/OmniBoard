"""Gestione dei provider IA configurabili (token salvati in DB, non in .env).

Definisce i provider noti (Qwen, Claude, OpenAI), li popola al primo avvio (con
migrazione opzionale del token Qwen da variabile d'ambiente) e fornisce la
configurazione del provider attivo all'IA. I token NON vengono mai restituiti in
lettura dall'API: si espone solo ``has_key``.
"""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from . import models, settings_service
from .opponents import api_ai

# Provider noti. base_url/model sono valori iniziali modificabili dal super admin.
PROVIDER_DEFS = [
    {
        "code": "qwen",
        "label": "Qwen (Alibaba DashScope)",
        "kind": "openai",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    {
        "code": "anthropic",
        "label": "Claude (Anthropic)",
        "kind": "anthropic",
        "base_url": "",  # vuoto = endpoint predefinito dell'SDK
        "model": "claude-opus-4-8",
    },
    {
        "code": "openai",
        "label": "OpenAI (compatibile)",
        "kind": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    {
        # Endpoint OpenAI-compatible di Google (AI Studio): /v1beta/openai + /chat/completions.
        "code": "gemini",
        "label": "Gemini (Google)",
        "kind": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.5-flash",
    },
    {
        # xAI espone un endpoint nativamente OpenAI-compatible.
        "code": "grok",
        "label": "Grok (xAI)",
        "kind": "openai",
        "base_url": "https://api.x.ai/v1",
        "model": "grok-4",
    },
]

_VALID = {d["code"] for d in PROVIDER_DEFS}


def seed_providers(db: Session) -> None:
    """Inserisce i provider mancanti (preservando i valori già impostati).

    Migrazione del token Qwen da ambiente (``QWEN_API_KEY``/``DASHSCOPE_API_KEY`` +
    ``QWEN_BASE_URL``/``QWEN_MODEL``): avviene sia alla creazione della riga, sia in
    *backfill* su un DB già esistente **solo se** Qwen non ha ancora un token (così non
    si sovrascrive quanto configurato dall'interfaccia super admin).

    NON attiva automaticamente alcun provider: l'attivazione è una scelta **esplicita**
    dal super admin. Attivare un provider non verificato (token errato, quota esaurita,
    endpoint irraggiungibile) farebbe partire chiamate remote inutili a ogni mossa; in
    assenza di provider attivo l'IA usa direttamente il giocatore locale.
    """
    env_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    for d in PROVIDER_DEFS:
        row = db.get(models.AiProvider, d["code"])
        if row is None:
            base_url = d["base_url"]
            model = d["model"]
            api_key = None
            if d["code"] == "qwen":
                base_url = os.getenv("QWEN_BASE_URL", base_url)
                model = os.getenv("QWEN_MODEL", model)
                api_key = env_key
            db.add(
                models.AiProvider(
                    code=d["code"],
                    label=d["label"],
                    kind=d["kind"],
                    base_url=base_url,
                    model=model,
                    api_key=api_key,
                )
            )
        else:  # allinea i metadati statici, preserva config/credenziali
            row.label = d["label"]
            row.kind = d["kind"]
            if d["code"] == "qwen" and not row.api_key and env_key:
                row.api_key = env_key
                row.base_url = os.getenv("QWEN_BASE_URL", row.base_url)
                row.model = os.getenv("QWEN_MODEL", row.model)
    db.commit()


def list_providers(db: Session) -> list[dict]:
    """Provider con la loro configurazione, SENZA esporre il token (solo has_key)."""
    rows = {r.code: r for r in db.query(models.AiProvider).all()}
    result = []
    for d in PROVIDER_DEFS:
        r = rows.get(d["code"])
        if r is None:
            continue
        result.append(
            {
                "code": r.code,
                "label": r.label,
                "kind": r.kind,
                "base_url": r.base_url or "",
                "model": r.model or "",
                "has_key": bool(r.api_key),
            }
        )
    return result


def is_known(code: str) -> bool:
    """True se il codice è nel catalogo dei provider (validazione al setup partita)."""
    return code in _VALID


def provider_label(code: str | None) -> str | None:
    """Etichetta leggibile di un provider («Gemini (Google)») per le viste."""
    return next((d["label"] for d in PROVIDER_DEFS if d["code"] == code), None)


def get_config(db: Session, code: str | None) -> dict | None:
    """Configurazione (con token) di un provider SPECIFICO; None se assente/senza token.

    È il cuore dei concorrenti IA multipli: ogni lato di una partita può indicare
    il proprio provider («gioca contro Claude», «gioca contro Gemini»), che viene
    risolto qui invece che dal solo provider attivo globale.
    """
    if not code:
        return None
    row = db.get(models.AiProvider, code)
    if row is None or not row.api_key:
        return None
    return {
        "code": row.code,
        "kind": row.kind,
        "base_url": row.base_url or "",
        "model": row.model or "",
        "api_key": row.api_key,
    }


def get_active_config(db: Session) -> dict | None:
    """Configurazione del provider attivo (con token) o None se assente/senza token."""
    return get_config(db, settings_service.get(db, "ai.provider"))


def update_providers(db: Session, active, providers: dict) -> None:
    """Aggiorna base_url/model/token dei provider e il provider attivo.

    Il token viene impostato solo se fornito non vuoto (un campo vuoto mantiene quello
    esistente). ``active`` può essere "" per disattivare l'IA remota.
    """
    for code, fields in (providers or {}).items():
        if code not in _VALID:
            continue
        row = db.get(models.AiProvider, code)
        if row is None:
            continue
        if "base_url" in fields:
            row.base_url = fields["base_url"]
        if "model" in fields:
            row.model = fields["model"]
        key = (fields.get("api_key") or "").strip()
        if key:
            row.api_key = key
    if active is not None and (active == "" or active in _VALID):
        settings_service.update_many(db, {"ai.provider": active})
    db.commit()


def test_provider(db: Session, code: str):
    """Verifica le credenziali di un provider con una chiamata minima."""
    row = db.get(models.AiProvider, code)
    if row is None:
        return False, "Provider sconosciuto"
    if not row.api_key:
        return False, "Nessun token configurato (salva prima il token)"
    config = {
        "code": row.code,
        "kind": row.kind,
        "base_url": row.base_url or "",
        "model": row.model or "",
        "api_key": row.api_key,
    }
    return api_ai.ping(config)
