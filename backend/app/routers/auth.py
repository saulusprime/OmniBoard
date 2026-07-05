"""Autenticazione dei giocatori: login/logout con sessione lato server.

Flusso completo:

1. Il giocatore invia una RICHIESTA di registrazione (``POST /users``): l'utente
   nasce con ``is_approved=False`` e la password è salvata subito e SOLO come
   hash PBKDF2 in anagrafica (``User.password_hash`` — vedi security.py).
2. Solo il super admin accetta la richiesta (``POST /users/{id}/approve``,
   header ``X-Admin-Token``) o la respinge (``DELETE /users/{id}``).
3. Da approvato, il giocatore fa login qui: riceve un token di sessione opaco
   (riga in ``auth_sessions``) da presentare come header ``X-Auth-Token``.
4. ``GET /auth/me`` riconosce il giocatore dal token; ``POST /auth/logout``
   cancella la sessione. Le sessioni scadute sono ripulite pigramente.

La durata della sessione è un parametro di programma (``users.session_hours``).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas, settings_service
from ..database import get_db
from ..security import verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    """SQLite restituisce datetime naive: li si tratta come UTC (come sono stati scritti)."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _purge_expired(db: Session) -> None:
    """Pulizia pigra: elimina le sessioni scadute (nessun job in background)."""
    now = _now().replace(tzinfo=None)  # confronto in SQL su valori naive-UTC
    db.query(models.AuthSession).filter(models.AuthSession.expires_at < now).delete()


def session_from_token(db: Session, token: str) -> models.AuthSession:
    """Risolve il token in una sessione valida, oppure 401 (mai dettagli sul perché)."""
    sess = (
        db.query(models.AuthSession).filter(models.AuthSession.token == token).first()
        if token
        else None
    )
    if not sess or _as_utc(sess.expires_at) <= _now():
        raise HTTPException(status_code=401, detail="Sessione non valida o scaduta")
    return sess


@router.post("/login", response_model=schemas.LoginOut)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    """Verifica le credenziali e apre una sessione.

    Alias sconosciuto, utente senza password e password errata producono lo
    STESSO 401: non si rivela quali account esistono (niente enumerazione).
    Il 403 per la richiesta non ancora approvata arriva solo DOPO la verifica
    della password: informa il legittimo proprietario, non un estraneo.
    """
    ident = payload.identifier.strip()
    user = (
        db.query(models.User)
        .filter(or_(models.User.alias == ident, models.User.email == ident))
        .first()
    )
    good = user and user.password_hash and verify_password(payload.password, user.password_hash)
    if not good:
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    if not user.is_approved:
        raise HTTPException(
            status_code=403,
            detail="Registrazione in attesa di approvazione da parte del super admin",
        )

    _purge_expired(db)
    hours = int(settings_service.get(db, "users.session_hours"))
    expires = _now() + timedelta(hours=hours)
    sess = models.AuthSession(
        token=secrets.token_urlsafe(32),
        user_id=user.id,
        expires_at=expires.replace(tzinfo=None),  # naive-UTC, coerente con la colonna
    )
    db.add(sess)
    user.last_seen_at = _now().replace(tzinfo=None)  # appena loggato = online
    db.commit()
    return schemas.LoginOut(
        token=sess.token, expires_at=expires, user=schemas.UserOut.model_validate(user)
    )


@router.get("/me", response_model=schemas.UserOut)
def me(
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Il giocatore riconosciuto dal token di sessione (o 401)."""
    sess = session_from_token(db, x_auth_token)
    return sess.user


@router.post("/heartbeat", status_code=204)
def heartbeat(
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Segnala che il giocatore è ancora davanti al client (presenza online).

    Il frontend lo chiama periodicamente; "online" = ultimo battito entro la
    finestra ``community.online_window_s`` (vedi router community).
    """
    sess = session_from_token(db, x_auth_token)
    sess.user.last_seen_at = _now().replace(tzinfo=None)
    db.commit()


@router.post("/logout", status_code=204)
def logout(
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Chiude la sessione. Idempotente: 204 anche se il token non esiste più."""
    sess = db.query(models.AuthSession).filter(models.AuthSession.token == x_auth_token).first()
    if sess:
        sess.user.last_seen_at = None  # uscita esplicita = subito offline in community
        db.delete(sess)
    _purge_expired(db)
    db.commit()
