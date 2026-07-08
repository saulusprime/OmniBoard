"""Endpoint per l'anagrafica giocatori."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import analysis, models, profile_cache, schemas, settings_service, tilt, user_prefs
from ..database import get_db
from ..i18n import _
from ..security import hash_password
from .admin import require_admin

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=schemas.UserOut, status_code=201)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    """Richiesta di registrazione di un nuovo giocatore.

    L'utente nasce NON approvato (``is_approved=False``): finché il super admin
    non accetta la richiesta il login è negato. La password, se fornita, viene
    salvata subito e solo come hash (mai in chiaro) in anagrafica.
    """
    if not settings_service.get(db, "users.allow_registration"):
        raise HTTPException(
            status_code=403, detail=_("Registrazioni disabilitate dall'amministratore")
        )
    if db.query(models.User).filter(models.User.alias == payload.alias).first():
        raise HTTPException(status_code=409, detail=_("Alias già in uso"))
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=409, detail=_("Email già registrata"))

    user = models.User(
        first_name=payload.first_name,
        last_name=payload.last_name,
        alias=payload.alias,
        email=payload.email,
        nationality=payload.nationality,
        region=payload.region,
        password_hash=hash_password(payload.password) if payload.password else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/{user_id}/approve",
    response_model=schemas.UserOut,
    dependencies=[Depends(require_admin)],
)
def approve_user(user_id: int, db: Session = Depends(get_db)):
    """Accetta la richiesta di registrazione: SOLO il super admin (X-Admin-Token)."""
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_("Utente non trovato"))
    user.is_approved = True
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204, dependencies=[Depends(require_admin)])
def reject_user(user_id: int, db: Session = Depends(get_db)):
    """Respinge (elimina) una richiesta di registrazione: solo il super admin.

    Per prudenza si possono eliminare SOLO gli utenti in attesa: un giocatore
    approvato ha storico e punteggi, la cancellazione non è contemplata qui.
    """
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_("Utente non trovato"))
    if user.is_approved:
        raise HTTPException(
            status_code=409, detail=_("Si può respingere solo una richiesta in attesa")
        )
    db.delete(user)
    db.commit()


@router.get("", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).order_by(models.User.alias).all()


@router.get("/{user_id}", response_model=schemas.UserDetail)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_("Utente non trovato"))
    scores = [
        schemas.ScoreOut(
            game_code=s.game.code,
            game_name=s.game.name,
            points=s.points,
            matches_played=s.matches_played,
            wins=s.wins,
            draws=s.draws,
            losses=s.losses,
        )
        for s in user.scores
    ]
    return schemas.UserDetail(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        alias=user.alias,
        email=user.email,
        nationality=user.nationality,
        region=user.region,
        is_approved=user.is_approved,
        prefs=user.prefs,
        created_at=user.created_at,
        universal_points=user.universal_points,
        scores=scores,
    )


@router.put("/{user_id}/prefs")
def update_user_prefs(
    user_id: int, payload: schemas.UserPrefsUpdate, db: Session = Depends(get_db)
):
    """Aggiorna le preferenze estetiche del giocatore (tema scacchiera, segno Tris).

    Sono opzioni personali, non parametri di programma: nessun token super admin.
    Vengono aggiornate solo le chiavi presenti nel payload.
    """
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_("Utente non trovato"))
    values = payload.model_dump(exclude_none=True)
    try:
        return user_prefs.update_prefs(db, user, values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{user_id}/chess-profile")
def chess_profile_endpoint(user_id: int, db: Session = Depends(get_db)):
    """Profilo scacchistico del giocatore: schemi (aperture), debolezze e stile derivato.

    È ciò che l'IA usa per adattare il proprio gioco quando affronta questo avversario.
    """
    profile = profile_cache.get(db, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=_("Utente non trovato"))
    return _translate_profile(profile)


_WEAKNESS_PATTERNS = [
    # Le debolezze PARAMETRIZZATE portano numeri/nomi dentro il testo in cache:
    # si riconoscono con una regex e si ricompongono nella lingua della risposta.
    (
        re.compile(r"Rende meno con l'apertura «(.+)»\."),
        lambda m: _("Rende meno con l'apertura «{name}».").format(name=_(m.group(1))),
    ),
    (
        re.compile(
            r"Commette blunder frequenti \(([\d.,]+) per partita, "
            r"analisi motore su (\d+) partite\)\."
        ),
        lambda m: _(
            "Commette blunder frequenti ({n} per partita, analisi motore su {games} partite)."
        ).format(n=m.group(1), games=m.group(2)),
    ),
    (
        re.compile(r"Precisione bassa: perde in media ([\d.,]+) centipedoni a mossa\."),
        lambda m: _("Precisione bassa: perde in media {acpl} centipedoni a mossa.").format(
            acpl=m.group(1)
        ),
    ),
]


def _translate_weakness(text: str) -> str:
    for pattern, build in _WEAKNESS_PATTERNS:
        m = pattern.fullmatch(text)
        if m:
            return build(m)
    return _(text)  # le debolezze a testo fisso passano dal catalogo


def _translate_profile(profile: dict) -> dict:
    """Copia del profilo coi testi nella lingua della richiesta.

    La CACHE del profilo è condivisa e resta in italiano (lingua sorgente): si
    traduce alla frontiera, su una copia superficiale delle parti testuali.
    """
    out = dict(profile)
    out["weaknesses"] = [_translate_weakness(w) for w in profile.get("weaknesses") or []]
    out["biases"] = [
        {**b, "label": _(b["label"]), "detail": _(b["detail"])} for b in profile.get("biases") or []
    ]
    out["openings"] = [{**o, "name": _(o["name"])} for o in profile.get("openings") or []]
    out["weakest_openings"] = [_(n) for n in profile.get("weakest_openings") or []]
    return out


@router.get("/{user_id}/tilt")
def tilt_endpoint(user_id: int, db: Session = Depends(get_db)):
    """Stato del tilt del giocatore: avviso soft con motivazioni ed esercizio."""
    state = tilt.assess(db, user_id)
    if state is None:
        raise HTTPException(status_code=404, detail=_("Utente non trovato"))
    return state


@router.post("/{user_id}/analyze-history")
def analyze_history_endpoint(user_id: int, db: Session = Depends(get_db)):
    """Analizza (in background) le ultime partite non ancora analizzate del giocatore.

    È il passo che RENDE RICCA la stima delle blunder del profilo: le analisi
    finiscono in cache (analysis_json) e il profilo le aggrega alla lettura dopo.
    """
    if not db.get(models.User, user_id):
        raise HTTPException(status_code=404, detail=_("Utente non trovato"))
    from ..opponents import stockfish

    if not stockfish.is_available(stockfish.get_config(db)):
        raise HTTPException(status_code=503, detail=_("Stockfish non disponibile per l'analisi"))
    return {"queued": analysis.analyze_history(db, user_id)}


@router.get("/{user_id}/history")
def user_history(user_id: int, db: Session = Depends(get_db)):
    """Storico delle partite concluse del giocatore, con il log delle mosse."""
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=_("Utente non trovato"))

    sessions = (
        db.query(models.GameSession)
        .filter(
            (models.GameSession.x_user_id == user_id) | (models.GameSession.o_user_id == user_id),
            models.GameSession.status == "finished",
        )
        .order_by(models.GameSession.created_at.desc())
        .all()
    )

    history = []
    for s in sessions:
        your_side = "x" if s.x_user_id == user_id else "o"
        if s.winner == "draw":
            result = "draw"
        elif s.winner == your_side:
            result = "win"
        else:
            result = "loss"
        if your_side == "x":
            opponent = "IA" if s.o_is_ai else (s.o_user.alias if s.o_user else "—")
        else:
            opponent = "IA" if s.x_is_ai else (s.x_user.alias if s.x_user else "—")
        history.append(
            {
                "session_id": s.id,
                "game_code": s.game.code,
                "game_name": s.game.name,
                "date": s.created_at,
                "your_side": your_side,
                "opponent": opponent,
                "result": result,
                "moves": json.loads(s.moves_json or "[]"),
            }
        )
    return history
