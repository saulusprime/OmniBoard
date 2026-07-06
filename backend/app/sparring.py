"""Sparring: il motore interno gioca contro Stockfish per MISURARE il proprio Elo.

Si gioca una serie di partite di scacchi (colori alternati) contro un preset con
Elo simulato noto (Atena 2700 … Pan 1400). Dal punteggio p si stima la differenza
Elo con la formula del modello logistico: ``diff = 400·log10(p/(1−p))``; l'Elo del
motore interno ≈ Elo del preset + diff. Con poche partite l'intervallo è ampio:
il risultato riporta anche il margine (±).

Il match gira in un thread (un solo sparring alla volta, è roba da CPU); lo stato
si legge in polling da ``GET /admin/sparring``. Con ``AI_ASYNC=0`` (test) è sincrono.
"""

from __future__ import annotations

import math
import os
import threading

from engine import get_game

from .opponents import local, stockfish

_lock = threading.Lock()
_state: dict = {"status": "idle"}

_MAX_PLIES = 240  # oltre = patta (protezione dalle partite infinite)


def state() -> dict:
    with _lock:
        return dict(_state)


def start(cfg: dict, level: str, games: int, engine_ms: int) -> tuple[bool, str]:
    """Avvia il match; (False, motivo) se non si può."""
    preset = stockfish.PRESETS.get(level)
    if not preset or not preset["elo"]:
        return False, "Serve un preset con Elo simulato (atena…pan): zeus non è misurabile"
    if not stockfish.is_available(cfg):
        return False, "Stockfish non disponibile (configura il binario)"
    with _lock:
        if _state.get("status") == "running":
            return False, "C'è già uno sparring in corso"
        _state.clear()
        _state.update(
            {
                "status": "running",
                "level": level,
                "base_elo": preset["elo"],
                "games_total": max(1, min(20, int(games))),
                "engine_ms": max(50, int(engine_ms)),
                "games": [],
            }
        )
    if os.getenv("AI_ASYNC", "1") == "0":
        _run(cfg)
    else:
        threading.Thread(target=_run, args=(cfg,), daemon=True).start()
    return True, "Sparring avviato"


def _play_one(game, sf_cfg: dict, engine_ms: int, engine_is_white: bool) -> str:
    """Una partita: ritorna "win"/"draw"/"loss" dal punto di vista del motore interno."""
    state_ = game.initial_state()
    history: list[str] = []
    while not game.is_terminal(state_) and len(history) < _MAX_PLIES:
        white_to_move = game.current_player(state_) == 0
        legal = list(game.legal_moves(state_))
        if white_to_move == engine_is_white:
            move, _src = local.best_move(game, state_, legal, history=history, think_ms=engine_ms)
        else:
            move = stockfish.best_move(game, state_, history, sf_cfg)
            if move is None:  # Stockfish caduto: partita non valida → patta tecnica
                return "draw"
        history.append(game.move_id(move))
        state_ = game.apply(state_, move)
    if not game.is_terminal(state_):
        return "draw"  # tetto di semimosse raggiunto
    winner = game.winner(state_)  # 0 = bianco, 1 = nero, None = patta
    if winner is None:
        return "draw"
    return "win" if (winner == 0) == engine_is_white else "loss"


def _run(cfg: dict) -> None:
    level = _state["level"]
    sf_cfg = stockfish.config_for_level(cfg, level)
    game = get_game("chess")
    total = _state["games_total"]
    for n in range(total):
        engine_is_white = n % 2 == 0  # colori alternati
        result = _play_one(game, sf_cfg, _state["engine_ms"], engine_is_white)
        with _lock:
            _state["games"].append(
                {
                    "n": n + 1,
                    "engine_color": "bianco" if engine_is_white else "nero",
                    "result": result,
                }
            )
    with _lock:
        results = [g["result"] for g in _state["games"]]
        wins = results.count("win")
        draws = results.count("draw")
        score = wins + draws * 0.5
        p = score / total
        # p=0 o p=1 → diff infinita: si stringe dentro il range misurabile.
        p_c = min(max(p, 1 / (2 * total)), 1 - 1 / (2 * total))
        diff = 400 * math.log10(p_c / (1 - p_c))
        # Margine ~ errore standard binomiale propagato sulla curva logistica.
        se = math.sqrt(max(p_c * (1 - p_c), 1e-6) / total)
        margin = 400 * (
            math.log10(min(p_c + se, 0.999) / (1 - min(p_c + se, 0.999)))
            - math.log10(p_c / (1 - p_c))
        )
        _state.update(
            {
                "status": "done",
                "score": f"{score:g}/{total}",
                "wins": wins,
                "draws": draws,
                "losses": results.count("loss"),
                "elo_estimate": round(_state["base_elo"] + diff),
                "elo_margin": round(abs(margin)),
            }
        )
