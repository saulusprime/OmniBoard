"""Giocatore IA.

Strategia: prova prima a far scegliere la mossa a **Qwen** (API DashScope, formato
OpenAI-compatible); se non è configurato o la risposta non è valida, ripiega su un
giocatore locale **ottimale** (minimax) — così il gioco è sempre giocabile.

Variabili d'ambiente:
- ``QWEN_API_KEY`` (o ``DASHSCOPE_API_KEY``): chiave API. Se assente, si usa solo il
  giocatore locale.
- ``QWEN_BASE_URL``: default endpoint internazionale DashScope (compatible-mode).
- ``QWEN_MODEL``: default ``qwen-plus``.
"""

from __future__ import annotations

import os
import re

import httpx

_SYSTEM_PROMPT = (
    "Sei un giocatore esperto di Tris (tic-tac-toe). "
    "Rispondi sempre e solo con il numero della casella scelta, senza altro testo."
)
_DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


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
        "Stato della griglia di Tris (caselle numerate 0-8, da sinistra a destra e "
        f"dall'alto in basso):\n{game.render_text(state)}\n\n"
        f"Tocca a te, giochi con il simbolo '{symbol}'. Caselle libere: {legal}.\n"
        "Scegli la casella migliore per vincere o non perdere. "
        "Rispondi SOLO con il numero della casella."
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


# ----- Giocatore locale (minimax ottimale) -----
def _local_move(game, state, legal):
    me = game.current_player(state)
    memo: dict = {}
    best_score, best_move = None, legal[0]
    for move in legal:
        score = _minimax(game, game.apply(state, move), me, memo)
        if best_score is None or score > best_score:
            best_score, best_move = score, move
    return best_move


def _minimax(game, state, me, memo):
    key = (state, me)
    if key in memo:
        return memo[key]
    if game.is_terminal(state):
        winner = game.outcome(state).winner
        value = 0 if winner is None else (1 if winner == me else -1)
    else:
        player = game.current_player(state)
        values = [_minimax(game, game.apply(state, m), me, memo) for m in game.legal_moves(state)]
        value = max(values) if player == me else min(values)
    memo[key] = value
    return value
