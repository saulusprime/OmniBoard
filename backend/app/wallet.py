"""Valuta virtuale («gettoni» 🪙): premi per l'attività di gioco.

MAI convertibile in denaro: è gamification pura, la primitiva che sbloccherà
pronostici da spettatori, ricompense per i creatori e mentorship. Si guadagna:

- giocando una partita fino in fondo (vittoria/patta/sconfitta, quest'ultima
  solo oltre ``coins.min_plies`` semimosse: l'abbandono immediato a catena
  non frutta nulla);
- risolvendo un puzzle per la PRIMA volta;
- completando una lezione del tutorial.

Il saldo è la SOMMA del registro ``wallet_transactions``; ogni premio è
IDEMPOTENTE per (utente, causale, riferimento) — rieseguire lo stesso evento
non accredita due volte. ``award*`` NON committa (transazione del chiamante),
come tutti gli hook di ``finalize_session``; il testo delle causali si
compone ALLA LETTURA nella lingua della richiesta, come le notifiche.
"""

from __future__ import annotations

import json

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models, settings_service
from .i18n import _

# Causale → template del testo mostrato nell'estratto conto.
_REASONS = {
    "game_win": "Vittoria in partita",
    "game_draw": "Patta in partita",
    "game_loss": "Partita giocata fino in fondo",
    "puzzle_solved": "Puzzle risolto",
    "lesson_completed": "Lezione completata",
}


def award(db: Session, user_id: int | None, amount: int, reason: str, ref: str | None) -> bool:
    """Accredita ``amount`` gettoni; False se il premio esiste già o non spetta."""
    if not user_id or amount <= 0:
        return False
    if ref is not None:
        db.flush()  # autoflush=False: senza flush il controllo non vede i pending
        exists = (
            db.query(models.WalletTransaction.id)
            .filter_by(user_id=user_id, reason=reason, ref=ref)
            .first()
        )
        if exists:
            return False  # idempotente: stesso evento, nessun doppio accredito
    db.add(models.WalletTransaction(user_id=user_id, amount=amount, reason=reason, ref=ref))
    return True


def balance(db: Session, user_id: int) -> int:
    total = (
        db.query(func.coalesce(func.sum(models.WalletTransaction.amount), 0))
        .filter_by(user_id=user_id)
        .scalar()
    )
    return int(total or 0)


def award_for_session(db: Session, session: models.GameSession) -> None:
    """Premi di fine partita ai lati UMANI (hook di finalize_session, no commit)."""
    plies = len(json.loads(session.moves_json or "[]"))
    if plies < int(settings_service.get(db, "coins.min_plies")):
        return  # partite lampo (abbandoni immediati): nessun gettone da farmare
    amounts = {
        "win": int(settings_service.get(db, "coins.win")),
        "draw": int(settings_service.get(db, "coins.draw")),
        "loss": int(settings_service.get(db, "coins.loss")),
    }
    ref = f"session:{session.id}"
    for side, uid in (("x", session.x_user_id), ("o", session.o_user_id)):
        if not uid:
            continue
        if session.winner == "draw":
            outcome = "draw"
        else:
            outcome = "win" if session.winner == side else "loss"
        award(db, uid, amounts[outcome], f"game_{outcome}", ref)


def statement(db: Session, user_id: int, limit: int = 20) -> dict:
    """Saldo + ultimi movimenti, coi testi nella lingua della richiesta."""
    rows = (
        db.query(models.WalletTransaction)
        .filter_by(user_id=user_id)
        .order_by(models.WalletTransaction.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "balance": balance(db, user_id),
        "transactions": [
            {
                "amount": r.amount,
                "text": _(_REASONS.get(r.reason, r.reason)),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }
