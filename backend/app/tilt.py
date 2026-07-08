"""Riconoscimento del TILT: la giornata storta si vede dai numeri.

Segnali (tutti da dati già esistenti, niente lavoro del motore):

- **sconfitte rapide consecutive** — le ultime N partite di scacchi concluse
  sono sconfitte sotto la soglia di semimosse (``tilt.quick_plies``): il segnale
  classico del «ancora una, veloce, mi rifaccio»;
- **ACPL recente sopra la propria media** — la perdita media per mossa nelle
  ultime partite ANALIZZATE supera la media storica del giocatore di un fattore
  (``tilt.acpl_factor``): si sta giocando peggio del proprio solito.

Risposta: **avviso SOFT** (banner nel setup, con un esercizio consigliato) — il
blocco forzato fa scappare i giocatori, quindi esiste solo come opzione admin
(``tilt.block``): a blocco attivo la creazione di una nuova partita di scacchi
viene rifiutata finché non è passato il raffreddamento (``tilt.block_cooldown_min``
dall'ultima sconfitta). Le partite in corso non vengono mai toccate.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import models, profile_cache, settings_service
from .i18n import _

CHESS_CODE = "chess"
_SAMPLE = 10  # quante partite recenti guardare
_RECENT_ANALYZED = 3  # su quante analisi recenti stimare l'ACPL "di oggi"

ADVICE = (
    "Fai una pausa di dieci minuti lontano dalla scacchiera, poi riscaldati con "
    "una lezione della sezione «Impara» (i finali elementari sono perfetti) "
    "prima di rigiocare una partita che conta."
)


def _user_side(session: models.GameSession, user_id: int) -> str:
    return "x" if session.x_user_id == user_id else "o"


def _recent_sessions(db: Session, user_id: int) -> list[models.GameSession]:
    return (
        db.query(models.GameSession)
        .join(models.Game)
        .filter(
            models.Game.code == CHESS_CODE,
            models.GameSession.status == "finished",
            or_(
                models.GameSession.x_user_id == user_id,
                models.GameSession.o_user_id == user_id,
            ),
        )
        .order_by(models.GameSession.id.desc())
        .limit(_SAMPLE)
        .all()
    )


def _recent_acpl(sessions, user_id: int) -> float | None:
    """ACPL delle mosse del giocatore nelle ultime partite analizzate."""
    losses: list[int] = []
    analyzed = 0
    for s in sessions:
        if analyzed >= _RECENT_ANALYZED or not s.analysis_json:
            continue
        try:
            data = json.loads(s.analysis_json)
        except ValueError:
            continue
        if data.get("status") != "done":
            continue
        side = _user_side(s, user_id)
        evals = [e for e in data.get("evals", []) if e.get("by") == side]
        if not evals:
            continue
        analyzed += 1
        losses.extend(min(int(e.get("loss") or 0), 1000) for e in evals)
    if not losses:
        return None
    return round(sum(losses) / len(losses), 1)


def assess(db: Session, user_id: int) -> dict | None:
    """Valutazione del tilt per il giocatore; None se l'utente non esiste."""
    if db.get(models.User, user_id) is None:
        return None
    enabled = bool(settings_service.get(db, "tilt.enabled"))
    losses_n = int(settings_service.get(db, "tilt.losses"))
    quick_plies = int(settings_service.get(db, "tilt.quick_plies"))
    factor = float(settings_service.get(db, "tilt.acpl_factor"))

    sessions = _recent_sessions(db, user_id)
    streak = quick_streak = 0
    last_loss_at = None
    for s in sessions:  # dalla più recente: la serie si interrompe al primo non-persa
        side = _user_side(s, user_id)
        lost = s.winner is not None and s.winner != "draw" and s.winner != side
        if not lost:
            break
        streak += 1
        if last_loss_at is None:
            last_loss_at = s.updated_at or s.created_at
        plies = len(json.loads(s.moves_json or "[]"))
        if plies <= quick_plies:
            quick_streak += 1

    recent_acpl = _recent_acpl(sessions, user_id)
    profile = profile_cache.get(db, user_id) or {}
    accuracy = profile.get("accuracy") or {}
    avg_acpl = accuracy.get("acpl")

    reasons = []
    if quick_streak >= losses_n:
        reasons.append(
            _("{n} sconfitte rapide di fila (≤{plies} semimosse)").format(
                n=quick_streak, plies=quick_plies
            )
        )
    acpl_high = recent_acpl is not None and avg_acpl and recent_acpl > float(avg_acpl) * factor
    if streak >= losses_n and acpl_high:
        reasons.append(
            _(
                "{n} sconfitte di fila con una precisione peggiore del solito "
                "(ACPL recente {rec} contro una media di {avg})"
            ).format(n=streak, rec=recent_acpl, avg=avg_acpl)
        )

    tilted = enabled and bool(reasons)
    return {
        "tilted": tilted,
        "reasons": reasons,
        "consecutive_losses": streak,
        "consecutive_quick_losses": quick_streak,
        "recent_acpl": recent_acpl,
        "avg_acpl": avg_acpl,
        "advice": _(ADVICE) if tilted else None,
        "last_loss_at": last_loss_at.isoformat() if last_loss_at else None,
    }


def block_new_game(db: Session, user_id: int) -> str | None:
    """Motivo del blocco anti-tilt per una NUOVA partita di scacchi, o None.

    Attivo solo con l'opzione admin ``tilt.block`` (il default è l'avviso soft) e
    solo entro il raffreddamento dall'ultima sconfitta: passato quello, si
    rigioca comunque.
    """
    if not settings_service.get(db, "tilt.block"):
        return None
    state = assess(db, user_id)
    if not state or not state["tilted"] or not state["last_loss_at"]:
        return None
    cooldown_min = int(settings_service.get(db, "tilt.block_cooldown_min"))
    last = datetime.fromisoformat(state["last_loss_at"])
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - last >= timedelta(minutes=cooldown_min):
        return None
    return (
        _("Pausa anti-tilt: ")
        + "; ".join(state["reasons"])
        + _(". Riprova tra ~{min} minuti — intanto: ").format(min=cooldown_min)
        + _(ADVICE)
    )
