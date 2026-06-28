"""Sessioni di gioco giocabili (umano vs umano, umano vs IA, IA vs IA).

Il backend mantiene lo stato della partita e il log delle mosse, valida le mosse
tramite il motore e fa giocare automaticamente i lati controllati dall'IA finché non
tocca a un umano o la partita finisce. A fine partita aggiorna i punteggi dei giocatori
umani; il log resta consultabile nello storico dei giocatori.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from engine.registry import get_game, is_playable

from .. import ai, models, schemas, services, settings_service
from ..database import get_db

router = APIRouter(prefix="/sessions", tags=["sessions"])

_CELL_SYMBOL = {0: "X", 1: "O", None: None}


def _load_state(game, session: models.GameSession):
    return game.deserialize_state(json.loads(session.state_json))


def _save_state(game, session: models.GameSession, state) -> None:
    session.state_json = json.dumps(game.serialize_state(state))


def _side_is_ai(session: models.GameSession, player: int) -> bool:
    return session.x_is_ai if player == 0 else session.o_is_ai


def _record_move(game, state_before, move, player: int, moves: list) -> None:
    moves.append(
        {
            "ply": len(moves) + 1,
            "player": "X" if player == 0 else "O",
            "notation": game.describe_move(state_before, move),
        }
    )


def _view(session: models.GameSession) -> dict:
    game = get_game(session.game.code)
    state = _load_state(game, session)
    data = game.serialize_state(state)
    finished = session.status == "finished"

    current = None
    current_is_ai = False
    legal: list[int] = []
    if not finished:
        player = game.current_player(state)
        current = "x" if player == 0 else "o"
        current_is_ai = _side_is_ai(session, player)
        legal = list(game.legal_moves(state))

    return {
        "id": session.id,
        "game_code": session.game.code,
        "status": session.status,
        "board": [_CELL_SYMBOL[c] for c in data["board"]],
        "current": current,
        "current_is_ai": current_is_ai,
        "legal_moves": legal,
        "winner": session.winner,
        "moves": json.loads(session.moves_json or "[]"),
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


def _finish_if_terminal(db: Session, game, session: models.GameSession, state) -> None:
    if session.status == "finished" or not game.is_terminal(state):
        return
    winner = game.outcome(state).winner
    session.winner = "draw" if winner is None else ("x" if winner == 0 else "o")
    session.status = "finished"
    services.finalize_session(db, session)
    db.commit()


def _advance_ai(db: Session, game, session: models.GameSession) -> None:
    """Fa giocare i lati IA finché non tocca a un umano o la partita finisce."""
    state = _load_state(game, session)
    moves = json.loads(session.moves_json or "[]")
    while not game.is_terminal(state):
        player = game.current_player(state)
        if not _side_is_ai(session, player):
            break
        cell, source = ai.choose_move(game, state)
        _record_move(game, state, cell, player, moves)
        state = game.apply(state, cell)
        session.last_ai_cell = cell
        session.last_ai_source = source
    session.moves_json = json.dumps(moves)
    _save_state(game, session, state)
    db.commit()
    _finish_if_terminal(db, game, session, state)


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

    _advance_ai(db, game, session)  # se il primo a muovere è l'IA, gioca subito
    return _view(session)


@router.post("/batch", status_code=201)
def run_batch(payload: schemas.BatchCreate, db: Session = Depends(get_db)):
    """Gioca ``count`` partite consecutive IA-vs-IA e restituisce il riepilogo.

    Non persiste le singole partite (nessun giocatore umano, nessun punteggio): è una
    simulazione. Con Qwen configurato può richiedere tempo (molte chiamate all'API).
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

    tally = {"x": 0, "o": 0, "draw": 0}
    for _ in range(payload.count):
        state = game.initial_state()
        while not game.is_terminal(state):
            cell, _source = ai.choose_move(game, state)
            state = game.apply(state, cell)
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
    return _view(session)


@router.post("/{session_id}/move")
def make_move(session_id: int, payload: schemas.MoveIn, db: Session = Depends(get_db)):
    session = db.get(models.GameSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessione non trovata")
    if session.status == "finished":
        raise HTTPException(status_code=409, detail="Partita già conclusa")

    game = get_game(session.game.code)
    state = _load_state(game, session)
    player = game.current_player(state)
    if _side_is_ai(session, player):
        raise HTTPException(status_code=409, detail="È il turno dell'IA")
    if payload.cell not in game.legal_moves(state):
        raise HTTPException(status_code=400, detail="Mossa non valida")

    moves = json.loads(session.moves_json or "[]")
    _record_move(game, state, payload.cell, player, moves)
    state = game.apply(state, payload.cell)
    session.moves_json = json.dumps(moves)
    _save_state(game, session, state)
    session.last_ai_cell = None
    session.last_ai_source = None
    db.commit()

    _finish_if_terminal(db, game, session, state)
    if session.status != "finished":
        _advance_ai(db, game, session)
    return _view(session)
