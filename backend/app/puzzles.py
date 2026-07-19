"""Sistema PUZZLE: posizione + linea di soluzione verificata dal motore.

La primitiva della sezione «Visione» (sblocca tilt-breaker, Gatekeeper, Puzzle
Story). Un puzzle è una FEN col tratto al SOLUTORE e una linea UCI: le mosse
del solutore agli indici pari, le risposte forzate dell'avversario ai dispari.

Due sorgenti:

- **seed autoriale** (``seed_puzzles``): matti in 1 classici, VERIFICATI col
  motore all'inserimento (la mossa deve davvero dare matto);
- **generazione automatica dai blunder** (``generate_from_games``): per ogni
  «??» delle analisi in cache, la posizione DOPO il blunder diventa un puzzle
  «punisci l'errore»; la confutazione la calcola il motore locale al momento
  della generazione. Dedup per (partita, semimossa) via vincolo di unicità.

La verifica di un tentativo è STATELESS (``check_attempt``): il client manda
(step, mossa), il server rigioca ``fen + solution[:step]`` e confronta; alla
mossa finale accetta anche un MATTO ALTERNATIVO (se il puzzle chiede matto,
ogni matto vale — UX classica dei puzzle).
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from engine import get_game

from . import models
from .i18n import _

CHESS_CODE = "chess"

# Matti in 1 autoriali (fen, [soluzione], tema): verificati al seed col motore.
SEED_PUZZLES = [
    ("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1", ["a1a8"], "matto in 1"),
    ("k7/8/1K6/8/8/8/8/7R w - - 0 1", ["h1h8"], "matto in 1"),
    ("7k/8/5K2/8/8/8/8/6Q1 w - - 0 1", ["g1g7"], "matto in 1"),
    # Il matto del barbiere: tocca al NERO (il solutore gioca col Nero).
    ("rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2", ["d8h4"], "matto in 1"),
    # Due torri: Rh8# è la soluzione ufficiale, ma anche Rg8# è matto
    # (il matto alternativo viene accettato: v. check_attempt).
    ("k7/8/1K6/8/8/8/8/6RR w - - 0 1", ["h1h8"], "matto in 1"),
]


def _replay(game, fen: str, line: list[str]):
    """Stato dopo ``line`` a partire da ``fen``; None se la linea non è legale."""
    state = game.from_fen(fen)
    for uci in line:
        move = next((m for m in game.legal_moves(state) if game.move_id(m) == uci), None)
        if move is None:
            return None
        state = game.apply(state, move)
    return state


def _is_mate_for_solver(game, state, solver: int) -> bool:
    return game.is_terminal(state) and game.outcome(state).winner == solver


def seed_puzzles(db: Session) -> int:
    """Inserisce i puzzle autoriali MANCANTI (idempotente per FEN), verificandoli."""
    game_row = db.query(models.Game).filter_by(code=CHESS_CODE).first()
    if game_row is None:
        return 0
    game = get_game(CHESS_CODE)
    n = 0
    for fen, solution, theme in SEED_PUZZLES:
        if db.query(models.Puzzle).filter_by(fen=fen, source="manual").first():
            continue
        start = game.from_fen(fen)
        after = _replay(game, fen, solution)
        # Verifica autoriale: la linea è legale e finisce in matto per il solutore.
        if after is None or not _is_mate_for_solver(game, after, start.current):
            continue
        db.add(
            models.Puzzle(
                game_id=game_row.id,
                fen=fen,
                solution_json=json.dumps(solution),
                theme=theme,
                difficulty=1,
                source="manual",
            )
        )
        n += 1
    db.commit()
    return n


def generate_from_games(db: Session, user_id: int | None = None, limit: int = 50) -> int:
    """Genera puzzle dai «??» delle partite ANALIZZATE (confutazione dal motore).

    La posizione dopo il blunder diventa «trova il colpo»: la soluzione è la
    mossa migliore del motore locale (budget breve), tema e difficoltà da ciò
    che la mossa ottiene. Ritorna quanti puzzle nuovi sono stati creati.
    """
    game = get_game(CHESS_CODE)
    q = (
        db.query(models.GameSession)
        .join(models.Game)
        .filter(
            models.Game.code == CHESS_CODE,
            models.GameSession.status == "finished",
            models.GameSession.analysis_json.isnot(None),
        )
    )
    if user_id is not None:
        from sqlalchemy import or_

        q = q.filter(
            or_(
                models.GameSession.x_user_id == user_id,
                models.GameSession.o_user_id == user_id,
            )
        )
    created = 0
    for session in q.order_by(models.GameSession.id.desc()).all():
        if created >= limit:
            break
        try:
            data = json.loads(session.analysis_json)
        except ValueError:
            continue
        if data.get("status") != "done":
            continue
        moves = json.loads(session.moves_json or "[]")
        history = [m["id"] for m in moves if "id" in m]
        for entry in data.get("evals", []):
            if entry.get("tag") != "??" or created >= limit:
                continue
            ply = entry["ply"]
            if ply >= len(history):
                continue  # il blunder è l'ultima mossa: nessuna confutazione da giocare
            exists = (
                db.query(models.Puzzle)
                .filter_by(source_session_id=session.id, source_ply=ply)
                .first()
            )
            if exists:
                continue
            state = _replay_history(game, session, history[:ply])
            if state is None or game.is_terminal(state):
                continue
            best = game.engine_move(state, time_limit=0.8, jitter=0)
            if best is None:
                continue
            uci = game.move_id(best)
            after = game.apply(state, best)
            if _is_mate_for_solver(game, after, state.current):
                theme, difficulty = "matto in 1", 1
            elif "x" in game.describe_move(state, best):
                theme, difficulty = "colpo vincente", 2
            else:
                theme, difficulty = "punisci l'errore", 3
            loss = int(entry.get("loss") or 0)
            if loss >= 500:
                difficulty = max(1, difficulty - 1)  # blunder enormi = puzzle facili
            db.add(
                models.Puzzle(
                    game_id=session.game_id,
                    fen=game.to_fen(state),
                    solution_json=json.dumps([uci]),
                    theme=theme,
                    difficulty=difficulty,
                    source="auto",
                    source_session_id=session.id,
                    source_ply=ply,
                )
            )
            created += 1
    db.commit()
    return created


def _replay_history(game, session: models.GameSession, history: list[str]):
    """Stato dopo ``history`` dalla posizione iniziale della SESSIONE (FEN inclusa)."""
    state = game.from_fen(session.start_fen) if session.start_fen else game.initial_state()
    for uci in history:
        move = next((m for m in game.legal_moves(state) if game.move_id(m) == uci), None)
        if move is None:
            return None
        state = game.apply(state, move)
    return state


def puzzle_view(game, puzzle: models.Puzzle, step: int) -> dict | None:
    """Vista giocabile del puzzle allo ``step`` (mosse del solutore agli indici pari)."""
    solution = json.loads(puzzle.solution_json)
    if not (0 <= step <= len(solution)) or step % 2 == 1:
        return None
    state = _replay(game, puzzle.fen, solution[:step])
    if state is None:
        return None
    return {
        "id": puzzle.id,
        "theme": puzzle.theme,
        "difficulty": puzzle.difficulty,
        "source": puzzle.source,
        "step": step,
        "steps_total": len(solution),
        "to_move": "white" if state.current == 0 else "black",
        "board": game.view_board(state),
        "playable": game.legal_moves_view(state),
        "rows": game.rows,
        "cols": game.cols,
    }


def check_attempt(game, puzzle: models.Puzzle, step: int, uci: str) -> dict:
    """Esito di un tentativo: {correct, solved, reply, view}.

    ``reply`` è la risposta dell'avversario dalla linea (già applicata nella
    vista restituita). Alla mossa FINALE un matto alternativo vale come
    soluzione (se c'è matto, ogni matto è giusto).
    """
    solution = json.loads(puzzle.solution_json)
    if not (0 <= step < len(solution)) or step % 2 == 1:
        return {"error": _("Semimossa inesistente")}
    state = _replay(game, puzzle.fen, solution[:step])
    if state is None:
        return {"error": _("Storico non ricostruibile")}
    move = next((m for m in game.legal_moves(state) if game.move_id(m) == uci), None)
    if move is None:
        return {"correct": False, "solved": False, "reply": None}

    expected = solution[step]
    correct = uci == expected
    if not correct and step == len(solution) - 1:
        # Matto alternativo: accettato (il tema chiede il matto, non LA mossa).
        after = game.apply(state, move)
        correct = _is_mate_for_solver(game, after, state.current)
    if not correct:
        return {"correct": False, "solved": False, "reply": None}

    solved = step + 1 >= len(solution)
    reply = solution[step + 1] if not solved else None
    next_step = step + (1 if solved else 2)
    view_step = min(next_step, len(solution))
    # La vista dopo la mossa (e l'eventuale risposta): si rigioca la LINEA
    # ufficiale — con un matto alternativo la partita è comunque finita.
    line = solution[:step] + [uci] + ([reply] if reply else [])
    state_after = _replay(game, puzzle.fen, line)
    view = None
    if state_after is not None:
        view = {
            "board": game.view_board(state_after),
            "playable": [] if solved else game.legal_moves_view(state_after),
            "step": view_step,
        }
    return {"correct": True, "solved": solved, "reply": reply, "view": view}


def record_attempt(db: Session, user_id: int, puzzle_id: int, solved: bool) -> None:
    row = db.query(models.PuzzleAttempt).filter_by(user_id=user_id, puzzle_id=puzzle_id).first()
    if row is None:
        row = models.PuzzleAttempt(user_id=user_id, puzzle_id=puzzle_id)
        db.add(row)
        db.flush()
    row.attempts += 1
    if solved and not row.solved:
        # Prima soluzione: gettoni (idempotente anche per ref, doppia rete).
        from . import settings_service, wallet

        wallet.award(
            db,
            user_id,
            int(settings_service.get(db, "coins.puzzle")),
            "puzzle_solved",
            f"puzzle:{puzzle_id}",
        )
    if solved:
        row.solved = True
    db.commit()
