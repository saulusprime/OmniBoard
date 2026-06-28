"""Giocatore IA.

Strategia: prova prima a far scegliere la mossa a **Qwen** (API DashScope, formato
OpenAI-compatible); se non è configurato o la risposta non è valida, ripiega su un
giocatore locale (minimax) — così il gioco è sempre giocabile. La ricerca locale è
completa per i giochi piccoli (Tris) e limitata in profondità con euristica per quelli
grandi (Forza 4), in base a ``Game.search_depth``.

Variabili d'ambiente:
- ``QWEN_API_KEY`` (o ``DASHSCOPE_API_KEY``): chiave API. Se assente, si usa solo il
  giocatore locale.
- ``QWEN_BASE_URL``: default endpoint internazionale DashScope (compatible-mode).
- ``QWEN_MODEL``: default ``qwen-plus``.
"""

from __future__ import annotations

import os
import random
import re

import httpx

_SYSTEM_PROMPT = (
    "Sei un giocatore esperto di giochi da tavolo. "
    "Rispondi sempre e solo con il numero della mossa scelta, senza altro testo."
)
_DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
_WIN = 1_000_000.0


def choose_move(game, state) -> tuple[int, str]:
    """Sceglie una mossa legale. Ritorna (cella, sorgente) con sorgente 'qwen'|'local'."""
    legal = list(game.legal_moves(state))
    if not legal:
        raise ValueError("Nessuna mossa legale disponibile")

    move = _qwen_move(game, state, legal)
    if move is not None and move in legal:
        return move, "qwen"
    return _local_move(game, state, legal), "local"


# ----- Qwen -----
def _qwen_move(game, state, legal):
    api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return None
    base_url = os.getenv("QWEN_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
    model = os.getenv("QWEN_MODEL", "qwen-plus")
    symbol = "X" if game.current_player(state) == 0 else "O"
    prompt = (
        f"Gioco: {game.name}. Stato attuale (X e O, '.' = vuoto):\n"
        f"{game.render_text(state)}\n\n"
        f"Tocca a te, giochi con '{symbol}'. Mosse disponibili (indici): {legal}.\n"
        "Scegli la mossa migliore per vincere o non perdere. "
        "Rispondi SOLO con il numero della mossa."
    )
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None

    for token in re.findall(r"\d+", content):
        cell = int(token)
        if cell in legal:
            return cell
    return None


# ----- Giocatore locale (minimax, completo o a profondità limitata) -----
def _local_move(game, state, legal):
    me = game.current_player(state)
    depth = getattr(game, "search_depth", None)
    memo: dict | None = {} if depth is None else None  # memoization solo a ricerca completa
    best_score = None
    best_moves: list = []
    for move in legal:
        next_depth = None if depth is None else depth - 1
        score = _search(game, game.apply(state, move), me, next_depth, memo)
        if best_score is None or score > best_score:
            best_score = score
            best_moves = [move]
        elif score == best_score:
            best_moves.append(move)
    # Scelta casuale tra le mosse ugualmente ottimali: le partite consecutive variano.
    return random.choice(best_moves)


def _search(game, state, me, depth, memo):
    if memo is not None:
        key = (state, depth, me)
        if key in memo:
            return memo[key]
    if game.is_terminal(state):
        winner = game.outcome(state).winner
        value = 0.0 if winner is None else (_WIN if winner == me else -_WIN)
    elif depth == 0:
        value = float(game.heuristic(state, me))
    else:
        player = game.current_player(state)
        next_depth = None if depth is None else depth - 1
        scores = [
            _search(game, game.apply(state, m), me, next_depth, memo)
            for m in game.legal_moves(state)
        ]
        value = max(scores) if player == me else min(scores)
    if memo is not None:
        memo[key] = value
    return value
