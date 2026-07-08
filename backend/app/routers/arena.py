"""Arena delle IA: classifica Elo dei concorrenti e tornei IA-vs-IA.

La classifica si alimenta da ogni partita IA-vs-IA conclusa (vedi
``services.finalize_session``); i tornei sono gironi all'italiana giocati in
sequenza da un thread — le partite sono vere sessioni, consultabili con
moviola, analisi e PGN dallo storico.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine import is_playable

from .. import ai_arena, models
from ..database import get_db
from ..i18n import _

router = APIRouter(prefix="/arena", tags=["arena"])


@router.get("/identities")
def list_identities():
    """Catalogo dei concorrenti IA (per il form di creazione torneo)."""
    return ai_arena.identities()


@router.get("/ranking/{game_code}")
def ai_ranking(game_code: str, db: Session = Depends(get_db)):
    """Classifica Elo delle IA nel gioco (ordinata dal rating più alto)."""
    game = db.query(models.Game).filter_by(code=game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail=_("Gioco non trovato"))
    return {"game_code": game_code, "rows": ai_arena.ranking(db, game.id)}


class TournamentCreate(BaseModel):
    game_code: str = "chess"
    # Identità dei concorrenti (codici del catalogo /arena/identities), 2-8 voci.
    participants: list[str]
    # Doppio girone = andata e ritorno a colori invertiti.
    double_round: bool = False
    name: str = ""


def _tournament_view(t: models.Tournament, db: Session, detail: bool = False) -> dict:
    played = sum(1 for g in t.games if g.result is not None)
    view = {
        "id": t.id,
        "name": t.name,
        "game_code": t.game.code,
        "game_name": t.game.name,
        "status": t.status,
        "double_round": t.double_round,
        "games_played": played,
        "games_total": len(t.games),
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
    if detail:
        view["standings"] = ai_arena.standings(db, t)
        view["games"] = [
            {
                "id": g.id,
                "x_identity": g.x_identity,
                "x_label": ai_arena.label_of(g.x_identity),
                "o_identity": g.o_identity,
                "o_label": ai_arena.label_of(g.o_identity),
                "session_id": g.session_id,
                "result": g.result,
            }
            for g in sorted(t.games, key=lambda g: g.id)
        ]
    return view


@router.post("/tournaments", status_code=201)
def create_tournament(payload: TournamentCreate, db: Session = Depends(get_db)):
    game = db.query(models.Game).filter_by(code=payload.game_code).first()
    if not game or not is_playable(payload.game_code):
        raise HTTPException(status_code=404, detail=_("Gioco non trovato o non giocabile"))
    participants = list(dict.fromkeys(payload.participants))  # dedup, ordine stabile
    if not 2 <= len(participants) <= ai_arena.MAX_PARTICIPANTS:
        raise HTTPException(
            status_code=400,
            detail=_("Servono da 2 a {n} concorrenti diversi").format(n=ai_arena.MAX_PARTICIPANTS),
        )
    unknown = [c for c in participants if not ai_arena.is_known(c)]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=_("Concorrenti sconosciuti: {codes}").format(codes=unknown),
        )

    tournament = models.Tournament(
        game_id=game.id,
        name=payload.name.strip() or f"Torneo {game.name}",
        double_round=payload.double_round,
        status="running",
    )
    db.add(tournament)
    db.flush()
    for x_identity, o_identity in ai_arena.build_pairings(participants, payload.double_round):
        db.add(
            models.TournamentGame(
                tournament_id=tournament.id, x_identity=x_identity, o_identity=o_identity
            )
        )
    db.commit()
    db.refresh(tournament)
    ai_arena.start(tournament.id)  # thread; sincrono nei test (AI_ASYNC=0)
    # Il runner usa un'ALTRA sessione DB: si invalida la cache locale prima di
    # leggere (in sincrono il torneo è già concluso qui).
    db.expire_all()
    return _tournament_view(db.get(models.Tournament, tournament.id), db, detail=True)


@router.get("/tournaments")
def list_tournaments(db: Session = Depends(get_db)):
    rows = db.query(models.Tournament).order_by(models.Tournament.id.desc()).all()
    return [_tournament_view(t, db) for t in rows]


@router.get("/tournaments/{tournament_id}")
def tournament_detail(tournament_id: int, db: Session = Depends(get_db)):
    t = db.get(models.Tournament, tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail=_("Torneo non trovato"))
    return _tournament_view(t, db, detail=True)
