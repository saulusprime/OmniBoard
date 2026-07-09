"""Notifiche persistenti: campanella in navbar, lette via polling.

Il testo NON è persistito: si salva ``kind`` + parametri e la frase si compone
alla LETTURA nella lingua della richiesta (stesso schema di tilt e debolezze:
i dati restano italiani/neutri, la traduzione avviene alla frontiera).

``notify`` NON committa: si accoda alla transazione del chiamante (endpoint o
hook di ``finalize_session``), che committa subito dopo — come punti e rating.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from . import models
from .i18n import _

# kind → frase parametrica (tradotta con _() alla lettura, poi .format()).
_TEMPLATES = {
    "game_invite": "{alias} ti sfida a {game}",
    "invite_accepted": "{alias} ha accettato la tua sfida a {game}",
    "invite_declined": "{alias} ha rifiutato la tua sfida a {game}",
    "group_invite": "Il gruppo «{group}» ti invita (da {alias})",
    "tournament_game": "Torneo «{name}»: è pronta la tua partita del turno {round}",
    "tournament_won": "Hai vinto il torneo «{name}»!",
    "tournament_finished": "Torneo «{name}» concluso: vince {alias}",
}

# Oltre questa soglia le notifiche lette più vecchie vengono potate (per utente).
_KEEP_READ = 50


def notify(db: Session, user_id: int, kind: str, **params) -> None:
    """Accoda una notifica (senza commit). I parametri extra viaggiano nel JSON.

    Oltre ai segnaposto del template, ``params`` può portare gli id per i link
    del client: ``session_id``, ``tournament_id``, ``group_id``, ``invite_id``.
    """
    db.add(
        models.Notification(
            user_id=user_id,
            kind=kind,
            params_json=json.dumps(params, ensure_ascii=False),
        )
    )


def render(n: models.Notification) -> dict:
    """La notifica pronta per il client, col testo nella lingua della richiesta."""
    try:
        params = json.loads(n.params_json or "{}")
    except ValueError:
        params = {}
    template = _TEMPLATES.get(n.kind, n.kind)
    try:
        text = _(template).format(**params)
    except (KeyError, IndexError):  # parametri storici incompleti: meglio grezzo
        text = _(template)
    return {
        "id": n.id,
        "kind": n.kind,
        "text": text,
        "read": n.read,
        "session_id": params.get("session_id"),
        "tournament_id": params.get("tournament_id"),
        "group_id": params.get("group_id"),
        "invite_id": params.get("invite_id"),
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


def list_for(db: Session, user_id: int, limit: int = 30) -> dict:
    """Le notifiche più recenti dell'utente + il conteggio delle non lette."""
    rows = (
        db.query(models.Notification)
        .filter_by(user_id=user_id)
        .order_by(models.Notification.id.desc())
        .limit(limit)
        .all()
    )
    unread = db.query(models.Notification).filter_by(user_id=user_id, read=False).count()
    return {"unread": unread, "notifications": [render(n) for n in rows]}


def mark_read(db: Session, user_id: int, ids: list[int] | None = None) -> int:
    """Segna come lette (tutte, o solo ``ids``); ritorna quante righe ha toccato.

    Già che passa, PODA le lette più vecchie oltre ``_KEEP_READ``: la tabella
    non cresce per sempre (le notifiche sono avvisi, non uno storico).
    """
    q = db.query(models.Notification).filter_by(user_id=user_id, read=False)
    if ids:
        q = q.filter(models.Notification.id.in_(ids))
    n = q.update({"read": True}, synchronize_session=False)
    stale = (
        db.query(models.Notification)
        .filter_by(user_id=user_id, read=True)
        .order_by(models.Notification.id.desc())
        .offset(_KEEP_READ)
        .all()
    )
    for row in stale:
        db.delete(row)
    db.commit()
    return n
