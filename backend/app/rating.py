"""Rating Elo dei giocatori umani (per gioco e per stagione).

Sostituisce lo schema punti 3/1/0 come MISURA DI FORZA (i punti restano come
misura di attività/gamification generale). Formula Elo classica con **K
adattivo stile FIDE**:

- K = 40 per i primi 30 incontri (rating «provvisorio»: si assesta in fretta);
- K = 20 fino a 2400;
- K = 10 oltre (i rating alti si muovono piano).

Si aggiorna SOLO sulle partite **umano-vs-umano** concluse (hotseat comprese,
come i punti): le partite contro le IA non toccano il rating — il pool delle IA
vive nell'arena e mescolare i due pool distorcerebbe entrambi.

**Stagioni**: la chiave è (utente, gioco, stagione) col parametro ``elo.season``;
cambiare la stagione dal pannello admin fa ripartire tutti da 1500, le righe
delle stagioni passate restano come storico consultabile.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from . import models, settings_service

START = 1500.0
PROVISIONAL_GAMES = 30  # sotto questa soglia il rating è dichiarato provvisorio


def season(db: Session) -> str:
    return str(settings_service.get(db, "elo.season") or "")


def k_factor(row: models.Rating) -> int:
    """K adattivo alla FIDE: nuovo giocatore svelto, rating alto stabile."""
    if row.games < PROVISIONAL_GAMES:
        return 40
    if row.elo < 2400:
        return 20
    return 10


def expected(ra: float, rb: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))


def get_or_create(db: Session, user_id: int, game_id: int, current_season: str) -> models.Rating:
    row = (
        db.query(models.Rating)
        .filter_by(user_id=user_id, game_id=game_id, season=current_season)
        .first()
    )
    if row is None:
        row = models.Rating(
            user_id=user_id, game_id=game_id, season=current_season, elo=START, peak_elo=START
        )
        db.add(row)
        db.flush()
    return row


def update_pair(db: Session, session: models.GameSession) -> None:
    """Aggiorna i rating dei due UMANI a partita conclusa (chiamata da finalize).

    Nessun effetto se un lato è IA, se manca un utente o se i due lati sono lo
    stesso utente (partita con sé stessi: nessuna informazione).
    """
    if session.x_is_ai or session.o_is_ai or session.winner is None:
        return
    x_uid, o_uid = session.x_user_id, session.o_user_id
    if not x_uid or not o_uid or x_uid == o_uid:
        return
    current = season(db)
    rx = get_or_create(db, x_uid, session.game_id, current)
    ro = get_or_create(db, o_uid, session.game_id, current)
    sx = {"x": 1.0, "o": 0.0, "draw": 0.5}[session.winner]
    ex = expected(rx.elo, ro.elo)  # dalle valutazioni PRIMA della partita
    rx.elo += k_factor(rx) * (sx - ex)
    ro.elo += k_factor(ro) * ((1.0 - sx) - (1.0 - ex))
    for row, score in ((rx, sx), (ro, 1.0 - sx)):
        row.games += 1
        if score == 1.0:
            row.wins += 1
        elif score == 0.0:
            row.losses += 1
        else:
            row.draws += 1
        row.peak_elo = max(row.peak_elo, row.elo)


def leaderboard(db: Session, game_id: int, current_season: str, limit: int = 100) -> list[dict]:
    rows = (
        db.query(models.Rating)
        .filter_by(game_id=game_id, season=current_season)
        .order_by(models.Rating.elo.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "rank": i + 1,
            "user_id": r.user_id,
            "alias": r.user.alias,
            "elo": round(r.elo),
            "peak_elo": round(r.peak_elo),
            "games": r.games,
            "wins": r.wins,
            "draws": r.draws,
            "losses": r.losses,
            "provisional": r.games < PROVISIONAL_GAMES,
        }
        for i, r in enumerate(rows)
    ]


def for_user(db: Session, user_id: int, current_season: str) -> list[dict]:
    rows = (
        db.query(models.Rating)
        .filter_by(user_id=user_id, season=current_season)
        .order_by(models.Rating.elo.desc())
        .all()
    )
    return [
        {
            "game_code": r.game.code,
            "game_name": r.game.name,
            "season": r.season,
            "elo": round(r.elo),
            "peak_elo": round(r.peak_elo),
            "games": r.games,
            "provisional": r.games < PROVISIONAL_GAMES,
        }
        for r in rows
    ]
