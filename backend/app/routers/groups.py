"""Endpoint per gruppi: fondazione tramite voto e GESTIONE del gruppo fondato.

Un gruppo si fonda quando una proposta raccoglie un numero di voti a favore pari
alla soglia (default 2). I votanti a favore diventano i membri fondatori.

Gestione (autenticata col token, ruoli founder > admin > member):

- **inviti**: founder/admin invitano; l'invitato accetta o rifiuta (mai
  ingressi d'ufficio). Un solo invito per (gruppo, utente): il re-invito
  riporta la riga a ``pending``.
- **ruoli**: solo il founder promuove/degrada gli admin;
- **espulsioni**: il founder espelle chiunque (tranne sé), l'admin solo i
  member; chiunque può lasciare il gruppo tranne il founder;
- **classifica di gruppo**: i membri ordinati per punti del gioco scelto
  (con Elo stagionale) o per punteggio complessivo.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .. import models, rating, schemas, settings_service
from ..database import get_db
from ..i18n import _
from .auth import session_from_token

router = APIRouter(prefix="/groups", tags=["groups"])

MANAGER_ROLES = ("founder", "admin")


def _actor(db: Session, token: str) -> models.User:
    return db.get(models.User, session_from_token(db, token).user_id)


def _membership(db: Session, group_id: int, user_id: int) -> models.GroupMembership | None:
    return db.query(models.GroupMembership).filter_by(group_id=group_id, user_id=user_id).first()


def _require_manager(db: Session, group_id: int, user_id: int) -> models.GroupMembership:
    m = _membership(db, group_id, user_id)
    if m is None or m.role not in MANAGER_ROLES:
        raise HTTPException(
            status_code=403, detail=_("Servono i gradi di fondatore o admin del gruppo")
        )
    return m


def _invite_out(inv: models.GroupInvite) -> schemas.InviteOut:
    return schemas.InviteOut(
        id=inv.id,
        group_id=inv.group_id,
        group_name=inv.group.name,
        user_id=inv.user_id,
        alias=inv.user.alias,
        invited_by_alias=inv.inviter.alias,
        status=inv.status,
        created_at=inv.created_at,
    )


def _proposal_out(p: models.GroupProposal) -> schemas.ProposalOut:
    return schemas.ProposalOut(
        id=p.id,
        name=p.name,
        proposed_by=p.proposed_by,
        status=p.status,
        threshold=p.threshold,
        favor_count=p.favor_count,
        group_id=p.group_id,
        created_at=p.created_at,
    )


def _group_out(g: models.Group) -> schemas.GroupOut:
    return schemas.GroupOut(
        id=g.id,
        name=g.name,
        created_at=g.created_at,
        members=[
            schemas.MembershipOut(user_id=m.user_id, alias=m.user.alias, role=m.role)
            for m in g.memberships
        ],
    )


# ----- Proposte di fondazione -----
@router.post("/proposals", response_model=schemas.ProposalOut, status_code=201)
def create_proposal(payload: schemas.GroupProposalCreate, db: Session = Depends(get_db)):
    proposer = db.get(models.User, payload.proposed_by)
    if not proposer:
        raise HTTPException(status_code=404, detail="Utente proponente non trovato")
    min_votes = int(settings_service.get(db, "groups.min_votes_to_found"))
    threshold = max(min_votes, payload.threshold)

    proposal = models.GroupProposal(
        name=payload.name, proposed_by=payload.proposed_by, threshold=threshold
    )
    db.add(proposal)
    db.flush()
    # Il proponente vota automaticamente a favore.
    db.add(
        models.GroupProposalVote(
            proposal_id=proposal.id, user_id=payload.proposed_by, in_favor=True
        )
    )
    db.commit()
    db.refresh(proposal)
    _maybe_found(proposal, db)
    db.refresh(proposal)
    return _proposal_out(proposal)


@router.get("/proposals", response_model=list[schemas.ProposalOut])
def list_proposals(db: Session = Depends(get_db)):
    proposals = (
        db.query(models.GroupProposal).order_by(models.GroupProposal.created_at.desc()).all()
    )
    return [_proposal_out(p) for p in proposals]


@router.post("/proposals/{proposal_id}/vote", response_model=schemas.ProposalOut)
def vote_proposal(proposal_id: int, payload: schemas.VoteCreate, db: Session = Depends(get_db)):
    proposal = db.get(models.GroupProposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposta non trovata")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail="Proposta già conclusa")
    if not db.get(models.User, payload.user_id):
        raise HTTPException(status_code=404, detail="Utente non trovato")

    existing = (
        db.query(models.GroupProposalVote)
        .filter_by(proposal_id=proposal_id, user_id=payload.user_id)
        .first()
    )
    if existing:
        existing.in_favor = payload.in_favor
    else:
        db.add(
            models.GroupProposalVote(
                proposal_id=proposal_id,
                user_id=payload.user_id,
                in_favor=payload.in_favor,
            )
        )
    db.commit()
    db.refresh(proposal)
    _maybe_found(proposal, db)
    db.refresh(proposal)
    return _proposal_out(proposal)


def _maybe_found(proposal: models.GroupProposal, db: Session) -> None:
    """Se i voti a favore raggiungono la soglia, fonda il gruppo."""
    if proposal.status != "pending" or proposal.favor_count < proposal.threshold:
        return
    group = models.Group(name=proposal.name)
    db.add(group)
    db.flush()
    for vote in proposal.votes:
        if vote.in_favor:
            role = "founder" if vote.user_id == proposal.proposed_by else "member"
            db.add(models.GroupMembership(group_id=group.id, user_id=vote.user_id, role=role))
    proposal.status = "founded"
    proposal.group_id = group.id
    db.commit()


# ----- Gruppi fondati -----
@router.get("", response_model=list[schemas.GroupOut])
def list_groups(db: Session = Depends(get_db)):
    return [_group_out(g) for g in db.query(models.Group).all()]


# ----- Inviti (percorsi FISSI prima di /{group_id}: l'int non li cattura) -----
@router.get("/invites/mine", response_model=list[schemas.InviteOut])
def my_invites(
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Gli inviti PENDENTI dell'utente autenticato (da accettare o rifiutare)."""
    actor = _actor(db, x_auth_token)
    invites = (
        db.query(models.GroupInvite)
        .filter_by(user_id=actor.id, status="pending")
        .order_by(models.GroupInvite.created_at.desc())
        .all()
    )
    return [_invite_out(i) for i in invites]


@router.post("/invites/{invite_id}/respond", response_model=schemas.InviteOut)
def respond_invite(
    invite_id: int,
    payload: schemas.InviteRespond,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """L'invitato accetta (diventa membro) o rifiuta. Nessun altro può rispondere."""
    actor = _actor(db, x_auth_token)
    inv = db.get(models.GroupInvite, invite_id)
    if inv is None:
        raise HTTPException(status_code=404, detail=_("Invito non trovato"))
    if inv.user_id != actor.id:
        raise HTTPException(status_code=403, detail=_("L'invito non è per te"))
    if inv.status != "pending":
        raise HTTPException(status_code=409, detail=_("Invito già concluso"))
    inv.status = "accepted" if payload.accept else "declined"
    if payload.accept and _membership(db, inv.group_id, actor.id) is None:
        db.add(models.GroupMembership(group_id=inv.group_id, user_id=actor.id, role="member"))
    db.commit()
    db.refresh(inv)
    return _invite_out(inv)


@router.get("/{group_id}", response_model=schemas.GroupOut)
def get_group(group_id: int, db: Session = Depends(get_db)):
    group = db.get(models.Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Gruppo non trovato")
    return _group_out(group)


@router.post("/{group_id}/invites", response_model=schemas.InviteOut, status_code=201)
def invite_member(
    group_id: int,
    payload: schemas.InviteCreate,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Founder o admin invitano un utente; il re-invito riapre l'invito rifiutato."""
    if not db.get(models.Group, group_id):
        raise HTTPException(status_code=404, detail="Gruppo non trovato")
    actor = _actor(db, x_auth_token)
    _require_manager(db, group_id, actor.id)
    target = db.get(models.User, payload.user_id)
    if target is None:
        raise HTTPException(status_code=404, detail=_("Utente non trovato"))
    if _membership(db, group_id, target.id) is not None:
        raise HTTPException(status_code=409, detail=_("È già membro del gruppo"))
    inv = db.query(models.GroupInvite).filter_by(group_id=group_id, user_id=target.id).first()
    if inv is None:
        inv = models.GroupInvite(group_id=group_id, user_id=target.id, invited_by=actor.id)
        db.add(inv)
    else:
        if inv.status == "pending":
            raise HTTPException(status_code=409, detail=_("Invito già in attesa"))
        inv.status = "pending"
        inv.invited_by = actor.id
    db.commit()
    db.refresh(inv)
    return _invite_out(inv)


@router.delete("/{group_id}/members/{user_id}", response_model=schemas.GroupOut)
def remove_member(
    group_id: int,
    user_id: int,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Espulsione (founder: chiunque tranne sé; admin: solo i member) o uscita.

    L'uscita volontaria è la stessa DELETE su di sé; il founder non può
    lasciare il proprio gruppo (prima passa il testimone — ruoli).
    """
    group = db.get(models.Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Gruppo non trovato")
    actor = _actor(db, x_auth_token)
    target_m = _membership(db, group_id, user_id)
    if target_m is None:
        raise HTTPException(status_code=404, detail=_("Non è membro del gruppo"))
    if actor.id == user_id:
        if target_m.role == "founder":
            raise HTTPException(
                status_code=409, detail=_("Il fondatore non può lasciare il gruppo")
            )
    else:
        actor_m = _require_manager(db, group_id, actor.id)
        if target_m.role == "founder":
            raise HTTPException(status_code=409, detail=_("Il fondatore non si espelle"))
        if actor_m.role == "admin" and target_m.role != "member":
            raise HTTPException(status_code=403, detail=_("Un admin può espellere solo i member"))
    db.delete(target_m)
    db.commit()
    db.refresh(group)
    return _group_out(group)


@router.post("/{group_id}/members/{user_id}/role", response_model=schemas.GroupOut)
def change_role(
    group_id: int,
    user_id: int,
    payload: schemas.RoleChange,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Solo il FOUNDER promuove a admin o degrada a member (mai se stesso)."""
    group = db.get(models.Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Gruppo non trovato")
    actor = _actor(db, x_auth_token)
    actor_m = _membership(db, group_id, actor.id)
    if actor_m is None or actor_m.role != "founder":
        raise HTTPException(status_code=403, detail=_("Solo il fondatore cambia i ruoli"))
    if payload.role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail=_("Ruolo sconosciuto"))
    target_m = _membership(db, group_id, user_id)
    if target_m is None:
        raise HTTPException(status_code=404, detail=_("Non è membro del gruppo"))
    if target_m.role == "founder":
        raise HTTPException(status_code=409, detail=_("Il ruolo del fondatore non si tocca"))
    target_m.role = payload.role
    db.commit()
    db.refresh(group)
    return _group_out(group)


@router.get("/{group_id}/ranking")
def group_ranking(group_id: int, game_code: str | None = None, db: Session = Depends(get_db)):
    """Classifica INTERNA del gruppo: per gioco (punti + Elo stagionale) o complessiva."""
    group = db.get(models.Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Gruppo non trovato")
    game = None
    if game_code:
        game = db.query(models.Game).filter_by(code=game_code).first()
        if game is None:
            raise HTTPException(status_code=404, detail=_("Gioco non trovato"))
    season = rating.season(db)
    rows = []
    for m in group.memberships:
        entry = {
            "user_id": m.user_id,
            "alias": m.user.alias,
            "role": m.role,
            "universal_points": m.user.universal_points,
        }
        if game is not None:
            score = db.query(models.Score).filter_by(user_id=m.user_id, game_id=game.id).first()
            elo = (
                db.query(models.Rating)
                .filter_by(user_id=m.user_id, game_id=game.id, season=season)
                .first()
            )
            entry.update(
                points=score.points if score else 0,
                wins=score.wins if score else 0,
                draws=score.draws if score else 0,
                losses=score.losses if score else 0,
                elo=elo.elo if elo else None,
            )
        rows.append(entry)
    if game is not None:
        rows.sort(key=lambda r: (-r["points"], -(r["elo"] or 0), r["alias"]))
    else:
        rows.sort(key=lambda r: (-r["universal_points"], r["alias"]))
    return {"group_id": group.id, "name": group.name, "season": season, "ranking": rows}
