"""Sessioni di gioco giocabili (umano vs umano, umano vs IA, IA vs IA).

Il backend mantiene lo stato della partita e il log delle mosse e valida le mosse
tramite il motore. Le mosse dei lati IA vengono calcolate **in background** (vedi
``gameplay``): gli endpoint rispondono subito e il client si aggiorna via polling
di ``GET /sessions/{id}``. A fine partita i punteggi dei giocatori umani vengono
aggiornati; il log resta consultabile nello storico dei giocatori.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from engine import get_game, is_playable

from .. import ai, ai_providers, gameplay, models, schemas, settings_service
from ..database import get_db

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _view(session: models.GameSession) -> dict:
    game = get_game(session.game.code)
    state = gameplay.load_state(game, session)
    finished = session.status == "finished"

    current = None
    current_is_ai = False
    legal: list[int] = []
    playable_moves: list[dict] = []
    if not finished:
        player = game.current_player(state)
        current = "x" if player == 0 else "o"
        current_is_ai = gameplay.side_is_ai(session, player)
        # Per i giochi a indice (Tris/Forza 4) il client usa gli interi; per la dama
        # usa la lista strutturata `playable_moves` (origine/destinazione/catture).
        legal = [m for m in game.legal_moves(state) if isinstance(m, int)]
        playable_moves = game.legal_moves_view(state)

    moves = json.loads(session.moves_json or "[]")
    return {
        "id": session.id,
        "game_code": session.game.code,
        "game_name": game.name,
        "rows": game.rows,
        "cols": game.cols,
        "move_type": game.move_type,
        "status": session.status,
        "board": game.view_board(state),
        "current": current,
        "current_is_ai": current_is_ai,
        "ai_thinking": current_is_ai and gameplay.is_running(session.id),
        "legal_moves": legal,
        "playable_moves": playable_moves,
        "winner": session.winner,
        "opening": game.opening_name(gameplay.history_ids(moves)),
        "moves": moves,
        "players": {
            "x": {
                "type": "ai" if session.x_is_ai else "human",
                "user_id": session.x_user_id,
                "alias": session.x_user.alias if session.x_user else None,
            },
            "o": {
                "type": "ai" if session.o_is_ai else "human",
                "user_id": session.o_user_id,
                "alias": session.o_user.alias if session.o_user else None,
            },
        },
        "last_ai": (
            {"cell": session.last_ai_cell, "source": session.last_ai_source}
            if session.last_ai_cell is not None
            else None
        ),
    }


@router.post("", status_code=201)
def create_session(payload: schemas.SessionCreate, db: Session = Depends(get_db)):
    game_model = db.query(models.Game).filter_by(code=payload.game_code).first()
    if not game_model:
        raise HTTPException(status_code=404, detail="Gioco non trovato")
    if not is_playable(payload.game_code):
        raise HTTPException(status_code=400, detail="Gioco non ancora giocabile")
    game = get_game(payload.game_code)

    def resolve(spec: schemas.PlayerSpec):
        if spec.type == "ai":
            return None, True
        if not spec.user_id:
            raise HTTPException(status_code=400, detail="Manca l'utente per un giocatore umano")
        if not db.get(models.User, spec.user_id):
            raise HTTPException(status_code=404, detail="Utente non trovato")
        return spec.user_id, False

    x_uid, x_ai = resolve(payload.x)
    o_uid, o_ai = resolve(payload.o)

    state = game.initial_state()
    session = models.GameSession(
        game_id=game_model.id,
        x_user_id=x_uid,
        o_user_id=o_uid,
        x_is_ai=x_ai,
        o_is_ai=o_ai,
        state_json=json.dumps(game.serialize_state(state)),
        moves_json="[]",
        status="in_progress",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    gameplay.schedule_ai(db, session)  # se il primo a muovere è l'IA, pensa in background
    return _view(session)


@router.post("/batch", status_code=201)
def run_batch(payload: schemas.BatchCreate, db: Session = Depends(get_db)):
    """Gioca ``count`` partite consecutive IA-vs-IA e restituisce il riepilogo.

    Non persiste le singole partite (nessun giocatore umano, nessun punteggio): è una
    simulazione sincrona con budget motore ridotto.
    """
    if not db.query(models.Game).filter_by(code=payload.game_code).first():
        raise HTTPException(status_code=404, detail="Gioco non trovato")
    if not is_playable(payload.game_code):
        raise HTTPException(status_code=400, detail="Gioco non ancora giocabile")
    max_batch = int(settings_service.get(db, "games.batch_max"))
    if payload.count > max_batch:
        raise HTTPException(
            status_code=400, detail=f"Numero massimo di partite consecutive: {max_batch}"
        )
    game = get_game(payload.game_code)

    provider = ai_providers.get_active_config(db)
    # Nel batch il motore scacchi usa un tempo ridotto (tante partite × tante mosse) e un
    # po' di jitter per non ripetere identica la stessa partita (motore deterministico).
    batch_ms = min(120, int(settings_service.get(db, "ai.engine_ms")))
    tally = {"x": 0, "o": 0, "draw": 0}
    for _ in range(payload.count):
        state = game.initial_state()
        history: list[str] = []
        while not game.is_terminal(state):
            move, _source = ai.choose_move(
                game, state, history, provider, think_ms=batch_ms, jitter=20
            )
            history.append(game.move_id(move))
            state = game.apply(state, move)
        winner = game.outcome(state).winner
        key = "draw" if winner is None else ("x" if winner == 0 else "o")
        tally[key] += 1

    return {
        "game_code": payload.game_code,
        "count": payload.count,
        "x_wins": tally["x"],
        "o_wins": tally["o"],
        "draws": tally["draw"],
    }


@router.get("/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):
    session = db.get(models.GameSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessione non trovata")
    # Auto-ripristino: se è il turno dell'IA e nessun worker è attivo (es. server
    # riavviato a metà pensata), il polling stesso riprogramma il calcolo.
    gameplay.schedule_ai(db, session, sync_fallback=False)
    return _view(session)


@router.post("/{session_id}/move")
def make_move(session_id: int, payload: schemas.MoveIn, db: Session = Depends(get_db)):
    session = db.get(models.GameSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessione non trovata")
    if session.status == "finished":
        raise HTTPException(status_code=409, detail="Partita già conclusa")

    game = get_game(session.game.code)
    state = gameplay.load_state(game, session)
    player = game.current_player(state)
    if gameplay.side_is_ai(session, player):
        raise HTTPException(status_code=409, detail="È il turno dell'IA")
    chosen = next((m for m in game.legal_moves(state) if game.move_id(m) == payload.move), None)
    if chosen is None:
        raise HTTPException(status_code=400, detail="Mossa non valida")

    moves = json.loads(session.moves_json or "[]")
    gameplay.record_move(game, state, chosen, player, moves)
    state = game.apply(state, chosen)
    session.moves_json = json.dumps(moves)
    gameplay.save_state(game, session, state)
    session.last_ai_cell = None
    session.last_ai_source = None
    db.commit()

    gameplay.finish_if_terminal(db, game, session, state)
    if session.status != "finished":
        gameplay.schedule_ai(db, session)  # la risposta parte subito, l'IA pensa in background
    return _view(session)
