"""Endpoint per gruppi e fondazione tramite voto.

Un gruppo si fonda quando una proposta raccoglie un numero di voti a favore pari
alla soglia (default 2). I votanti a favore diventano i membri fondatori. Le regole
di gestione del gruppo (ruoli, inviti, espulsioni) saranno definite successivamente.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, settings_service
from ..database import get_db

router = APIRouter(prefix="/groups", tags=["groups"])


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


@router.get("/{group_id}", response_model=schemas.GroupOut)
def get_group(group_id: int, db: Session = Depends(get_db)):
    group = db.get(models.Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Gruppo non trovato")
    return _group_out(group)
