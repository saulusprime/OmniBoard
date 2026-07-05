"""Sessioni di gioco giocabili (umano vs umano, umano vs IA, IA vs IA).

Il backend mantiene lo stato della partita e il log delle mosse e valida le mosse
tramite il motore. Le mosse dei lati IA vengono calcolate **in background** (vedi
``gameplay``): gli endpoint rispondono subito e il client si aggiorna via polling
di ``GET /sessions/{id}``. A fine partita i punteggi dei giocatori umani vengono
aggiornati; il log resta consultabile nello storico dei giocatori.
"""

from __future__ import annotations

import json
import random

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from engine import get_game, is_playable

from .. import ai_providers, gameplay, models, opponents, schemas, settings_service, user_prefs
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
    # Preferenze estetiche dei giocatori umani (tema scacchiera, segno del Tris);
    # per i lati IA valgono i default. Se i due umani hanno scelto lo STESSO segno,
    # il lato O ripiega sul default per mantenere i segni distinguibili.
    x_prefs = user_prefs.get_prefs(session.x_user)
    o_prefs = user_prefs.get_prefs(session.o_user)
    x_mark = (x_prefs.get("tris_mark") or "X") if session.x_user else "X"
    o_mark = (o_prefs.get("tris_mark") or "O") if session.o_user else "O"
    if o_mark == x_mark:
        o_mark = "O" if x_mark != "O" else "X"
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
        "finish_reason": session.finish_reason,  # "time" = decisa dall'orologio
        "clock": gameplay.clock_view(session, game),  # None se partita senza orologio
        # Riga informativa specifica del gioco (es. "Dadi da giocare: 5 3" nel
        # backgammon); None per i giochi che non ne hanno bisogno.
        "status_line": game.view_status(state),
        "opening": game.opening_name(gameplay.history_ids(moves)),
        "moves": moves,
        "players": {
            # type ∈ {"human", "ai" (IA via API), "stockfish"} — vedi gameplay.side_kind.
            # level/level_label: preset Stockfish (es. "zeus" / «Zeus (Extreme)»).
            "x": {
                "type": gameplay.side_kind(session, 0),
                "user_id": session.x_user_id,
                "alias": session.x_user.alias if session.x_user else None,
                "level": session.x_ai_level,
                "level_label": opponents.stockfish.preset_label(session.x_ai_level),
                # Estetica scelta dal giocatore: tema scacchiera e segno del Tris.
                "board_theme": x_prefs.get("board_theme") if session.x_user else None,
                "mark": x_mark,
            },
            "o": {
                "type": gameplay.side_kind(session, 1),
                "user_id": session.o_user_id,
                "alias": session.o_user.alias if session.o_user else None,
                "level": session.o_ai_level,
                "level_label": opponents.stockfish.preset_label(session.o_ai_level),
                "board_theme": o_prefs.get("board_theme") if session.o_user else None,
                "mark": o_mark,
            },
        },
        # Ultima mossa IA: "source" dice chi ha giocato davvero (book / stockfish /
        # <provider> / engine / local); "cell" è valorizzata solo per i giochi a
        # indice (Tris/Forza 4), per scacchi/dama la mossa è un percorso.
        "last_ai": (
            {"cell": session.last_ai_cell, "source": session.last_ai_source}
            if session.last_ai_source is not None
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
        """(user_id, is_ai, ai_kind, level) per un lato: umano, IA via API o Stockfish."""
        if spec.type == "stockfish":
            # Il livello è un preset noto ("zeus", "atena", …) o None (parametri globali).
            if spec.level and spec.level not in opponents.stockfish.PRESETS:
                raise HTTPException(status_code=400, detail="Livello Stockfish sconosciuto")
            return None, True, spec.type, spec.level
        if spec.type == "ai":
            return None, True, spec.type, None
        if not spec.user_id:
            raise HTTPException(status_code=400, detail="Manca l'utente per un giocatore umano")
        if not db.get(models.User, spec.user_id):
            raise HTTPException(status_code=404, detail="Utente non trovato")
        return spec.user_id, False, None, None

    x_uid, x_ai, x_kind, x_level = resolve(payload.x)
    o_uid, o_ai, o_kind, o_level = resolve(payload.o)

    # Orologio di gioco (solo scacchi): valida categoria/minuti/incremento Fischer.
    try:
        time_control = gameplay.build_time_control(
            payload.game_code, payload.time_category, payload.time_base_min, payload.time_inc_s
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    state = game.initial_state()
    session = models.GameSession(
        game_id=game_model.id,
        x_user_id=x_uid,
        o_user_id=o_uid,
        x_is_ai=x_ai,
        o_is_ai=o_ai,
        x_ai_kind=x_kind,
        o_ai_kind=o_kind,
        x_ai_level=x_level,
        o_ai_level=o_level,
        state_json=json.dumps(game.serialize_state(state)),
        moves_json="[]",
        status="in_progress",
    )
    gameplay.init_clock(session, time_control)  # l'orologio di X parte da subito
    db.add(session)
    db.commit()
    db.refresh(session)

    gameplay.resolve_chance(db, session=session, game=game)  # es. primo tiro di dadi
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
    # Entrambi i lati sono IA di tipo "ai" (API con ripiego sul giocatore locale).
    batch_ms = min(120, int(settings_service.get(db, "ai.engine_ms")))
    tally = {"x": 0, "o": 0, "draw": 0}
    for _ in range(payload.count):
        state = game.initial_state()
        history: list[str] = []
        while not game.is_terminal(state):
            if game.is_chance_node(state):
                # Giochi stocastici (backgammon): nel batch il tiro dei dadi viene
                # estratto qui, senza log (la simulazione non viene persistita).
                outcomes = game.chance_outcomes(state)
                event = random.choices(
                    [e for e, _p in outcomes], weights=[p for _e, p in outcomes], k=1
                )[0]
                state = game.apply_chance(state, event)
                continue
            move, _source = opponents.choose_move(
                game, state, history, kind="ai", provider=provider, think_ms=batch_ms, jitter=20
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
    game = get_game(session.game.code)
    # Nodi del caso pigri: chi legge lo stato materializza l'eventuale tiro di dadi.
    gameplay.resolve_chance(db, game, session)
    # Bandierina pigra: l'orologio è autorevole anche se nessuno muove più — la
    # lettura di stato (il polling del client) chiude la partita a tempo scaduto.
    gameplay.check_time(db, game, session)
    # Auto-ripristino: se è il turno dell'IA e nessun worker è attivo (es. server
    # riavviato a metà pensata), il polling stesso riprogramma il calcolo.
    gameplay.schedule_ai(db, session, sync_fallback=False)
    return _view(session)


@router.post("/{session_id}/move")
def make_move(session_id: int, payload: schemas.MoveIn, db: Session = Depends(get_db)):
    session = db.get(models.GameSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessione non trovata")

    game = get_game(session.game.code)
    # Nodi del caso: se i dadi sono ancora da tirare, si tirano ora (server-side).
    gameplay.resolve_chance(db, game, session)
    # L'orologio decide prima della mossa: se il tempo del giocatore è già scaduto,
    # la partita viene chiusa e la mossa rifiutata.
    gameplay.check_time(db, game, session)
    if session.status == "finished":
        raise HTTPException(status_code=409, detail="Partita già conclusa")

    state = gameplay.load_state(game, session)
    player = game.current_player(state)
    if gameplay.side_is_ai(session, player):
        raise HTTPException(status_code=409, detail="È il turno dell'IA")
    chosen = next((m for m in game.legal_moves(state) if game.move_id(m) == payload.move), None)
    if chosen is None:
        raise HTTPException(status_code=400, detail="Mossa non valida")

    moves = json.loads(session.moves_json or "[]")
    # Scala il tempo pensato dall'orologio del giocatore (con incremento a mossa
    # completata); se la bandierina è caduta nel frattempo, la mossa arriva tardi.
    if not gameplay.consume_time(db, game, session, player, moves):
        raise HTTPException(status_code=409, detail="Tempo scaduto: partita conclusa")
    gameplay.record_move(game, state, chosen, player, moves)
    state = game.apply(state, chosen)
    session.moves_json = json.dumps(moves)
    gameplay.save_state(game, session, state)
    session.last_ai_cell = None
    session.last_ai_source = None
    db.commit()

    gameplay.finish_if_terminal(db, game, session, state)
    if session.status != "finished":
        # Se il turno è passato a un nodo del caso (backgammon: dadi del prossimo
        # giocatore), la risposta include già il tiro: chi gioca in locale in due
        # non deve aspettare un polling per vedere i propri dadi.
        gameplay.resolve_chance(db, game, session)
        gameplay.schedule_ai(db, session)  # la risposta parte subito, l'IA pensa in background
    return _view(session)
