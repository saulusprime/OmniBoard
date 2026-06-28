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
    "Rispondi sempre e solo con l'id esatto della mossa scelta, senza altro testo."
)
_DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
_WIN = 1_000_000.0
_POS_INF = float("inf")
_NEG_INF = float("-inf")


def choose_move(game, state, history=None):
    """Sceglie una mossa legale. Ritorna (mossa, sorgente) con sorgente 'book'|'qwen'|'local'.

    Ordine: libro delle aperture (se ``history`` è fornito e la posizione segue una linea
    nota) → Qwen → giocatore locale (minimax alpha-beta).
    """
    legal = list(game.legal_moves(state))
    if not legal:
        raise ValueError("Nessuna mossa legale disponibile")

    if history is not None:
        book = game.opening_move(state, history)
        if book is not None and book in legal:
            return book, "book"

    move = _qwen_move(game, state, legal)
    if move is not None and move in legal:
        return move, "qwen"
    return _local_move(game, state, legal), "local"


# ----- Qwen -----
def _match_move(game, legal, content):
    """Estrae dalla risposta del modello una mossa legale, confrontando per id.

    Funziona per ogni gioco (cella, colonna o percorso/UCI) perché usa
    ``game.move_id``. Ritorna l'oggetto-mossa o None.
    """
    id_to_move = {game.move_id(m): m for m in legal}
    text = content.strip().lower()
    for token in re.findall(r"[a-h0-9=qrbnx-]+", text):
        if token in id_to_move:
            return id_to_move[token]
    # Fallback: id contenuto nel testo (prima i più lunghi, per evitare prefissi).
    for move_id in sorted(id_to_move, key=len, reverse=True):
        if move_id in text:
            return id_to_move[move_id]
    return None


def _qwen_move(game, state, legal):
    api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return None
    base_url = os.getenv("QWEN_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
    model = os.getenv("QWEN_MODEL", "qwen-plus")
    timeout = float(os.getenv("QWEN_TIMEOUT", "10"))
    symbol = "X" if game.current_player(state) == 0 else "O"
    move_ids = [game.move_id(m) for m in legal]
    prompt = (
        f"Gioco: {game.name}. Stato attuale (X e O, '.' = vuoto):\n"
        f"{game.render_text(state)}\n\n"
        f"Tocca a te, giochi con '{symbol}'. Mosse legali disponibili (id): {move_ids}.\n"
        "Scegli la mossa migliore per vincere o non perdere. "
        "Rispondi SOLO con l'id esatto della mossa scelta (uno di quelli elencati)."
    )
    try:
        with httpx.Client(timeout=timeout) as client:
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

    return _match_move(game, legal, content)


# ----- Giocatore locale (minimax con potatura alpha-beta) -----
def _local_move(game, state, legal):
    me = game.current_player(state)
    depth = getattr(game, "search_depth", None)  # None = ricerca completa (giochi piccoli)
    best_score = None
    best_moves: list = []
    for move in legal:
        next_depth = None if depth is None else depth - 1
        score = _search(game, game.apply(state, move), me, next_depth, _NEG_INF, _POS_INF)
        if best_score is None or score > best_score:
            best_score = score
            best_moves = [move]
        elif score == best_score:
            best_moves.append(move)
    # Scelta casuale tra le mosse ugualmente ottimali: le partite consecutive variano.
    return random.choice(best_moves)


def _search(game, state, me, depth, alpha, beta):
    if game.is_terminal(state):
        winner = game.outcome(state).winner
        return 0.0 if winner is None else (_WIN if winner == me else -_WIN)
    if depth == 0:
        return float(game.heuristic(state, me))
    next_depth = None if depth is None else depth - 1
    if game.current_player(state) == me:
        value = _NEG_INF
        for m in game.legal_moves(state):
            value = max(value, _search(game, game.apply(state, m), me, next_depth, alpha, beta))
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        return value
    value = _POS_INF
    for m in game.legal_moves(state):
        value = min(value, _search(game, game.apply(state, m), me, next_depth, alpha, beta))
        beta = min(beta, value)
        if beta <= alpha:
            break
    return value
