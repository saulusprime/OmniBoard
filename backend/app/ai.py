"""Giocatore IA.

Ordine di scelta della mossa: **libro delle aperture** (se è fornito lo storico e la
posizione segue una linea nota) → **provider IA remoto** configurato (Qwen, Claude,
OpenAI, …) → **giocatore locale** (minimax con potatura alpha-beta).

I provider sono configurati dal super admin (token salvati in DB, non in ``.env``).
``provider`` è un dict {code, kind, base_url, model, api_key}:
- kind ``"openai"`` → endpoint OpenAI-compatible via httpx (Qwen/DashScope, OpenAI, …);
- kind ``"anthropic"`` → SDK ufficiale ``anthropic`` (Claude).
La ricerca locale è completa per i giochi piccoli (Tris) e a profondità limitata con
euristica per quelli grandi (Forza 4, Dama, Scacchi), in base a ``Game.search_depth``.
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
_WIN = 1_000_000.0
_POS_INF = float("inf")
_NEG_INF = float("-inf")


def _timeout() -> float:
    return float(os.getenv("AI_TIMEOUT", os.getenv("QWEN_TIMEOUT", "10")))


def _http_timeout() -> httpx.Timeout:
    """Timeout con connect breve.

    Un endpoint remoto irraggiungibile (es. un indirizzo IPv6 che non risponde e
    resta in SYN_SENT) deve fallire in fretta: altrimenti la chiamata IA — eseguita
    in linea nella richiesta di mossa — bloccherebbe a lungo il backend. Superato il
    connect/timeout si ripiega sul giocatore locale.
    """
    total = _timeout()
    return httpx.Timeout(total, connect=min(4.0, total))


def choose_move(game, state, history=None, provider=None, think_ms=None, style=None, jitter=0):
    """Sceglie una mossa legale. Ritorna (mossa, sorgente).

    Ordine: **libro delle aperture** → **motore dedicato** (se il gioco ne ha uno, es.
    scacchi: un alpha-beta profondo, più forte di un LLM) → **provider remoto** → **locale**.
    ``sorgente`` ∈ {'book', 'engine', <codice provider>, 'local'}.
    """
    legal = list(game.legal_moves(state))
    if not legal:
        raise ValueError("Nessuna mossa legale disponibile")

    if history is not None:
        book = game.opening_move(state, history)
        if book is not None and book in legal:
            return book, "book"

    # Motore dedicato (scacchi): analizza la scacchiera in profondità ed è più forte di
    # una mossa chiesta a un LLM, perciò ha la precedenza sul provider remoto.
    engine_move = getattr(game, "engine_move", None)
    if callable(engine_move):
        move = engine_move(
            state, history=history, time_limit=_engine_time(think_ms), style=style, jitter=jitter
        )
        if move is not None and move in legal:
            return move, "engine"

    if provider:
        move = _remote_move(game, state, legal, provider)
        if move is not None and move in legal:
            return move, provider.get("code") or "remote"

    return _local_move(game, state, legal), "local"


def _engine_time(think_ms=None) -> float:
    """Budget di tempo (secondi) per il motore dedicato.

    ``think_ms`` viene di norma dal parametro ``ai.engine_ms`` (super admin); se assente si
    usa ``AI_ENGINE_MS`` (default 2000). ``AI_ENGINE_MS_MAX``, se impostata, è un tetto
    massimo applicato sempre (kill-switch operativo; nei test la limita per velocità).
    """
    t = float(os.getenv("AI_ENGINE_MS", "2000")) if think_ms is None else float(think_ms)
    cap = os.getenv("AI_ENGINE_MS_MAX")
    if cap:
        t = min(t, float(cap))
    return max(0.05, t / 1000.0)


# ----- Provider IA remoti -----
def _build_prompt(game, state, legal):
    symbol = "X" if game.current_player(state) == 0 else "O"
    move_ids = [game.move_id(m) for m in legal]
    return (
        f"Gioco: {game.name}. Stato attuale (X e O, '.' = vuoto):\n"
        f"{game.render_text(state)}\n\n"
        f"Tocca a te, giochi con '{symbol}'. Mosse legali disponibili (id): {move_ids}.\n"
        "Scegli la mossa migliore per vincere o non perdere. "
        "Rispondi SOLO con l'id esatto della mossa scelta (uno di quelli elencati)."
    )


def _match_move(game, legal, content):
    """Estrae dalla risposta del modello una mossa legale, confrontando per id.

    Funziona per ogni gioco (cella, colonna o percorso/UCI) perché usa ``game.move_id``.
    """
    id_to_move = {game.move_id(m): m for m in legal}
    text = content.strip().lower()
    for token in re.findall(r"[a-h0-9=qrbnx-]+", text):
        if token in id_to_move:
            return id_to_move[token]
    for move_id in sorted(id_to_move, key=len, reverse=True):
        if move_id in text:
            return id_to_move[move_id]
    return None


def _openai_complete(provider, prompt):
    """Chiamata a un endpoint OpenAI-compatible (Qwen/DashScope, OpenAI, …)."""
    base_url = (provider.get("base_url") or "").rstrip("/")
    with httpx.Client(timeout=_http_timeout()) as client:
        response = client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {provider['api_key']}"},
            json={
                "model": provider.get("model"),
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


def _anthropic_complete(provider, prompt):
    """Chiamata a Claude tramite l'SDK ufficiale Anthropic (Messages API)."""
    import anthropic  # import pigro: dipendenza necessaria solo per il provider Claude

    client = anthropic.Anthropic(
        api_key=provider["api_key"],
        base_url=provider.get("base_url") or None,
        timeout=_http_timeout(),
        max_retries=0,
    )
    message = client.messages.create(
        model=provider.get("model") or "claude-opus-4-8",
        max_tokens=64,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    if getattr(message, "stop_reason", None) == "refusal":
        return None
    return "".join(b.text for b in message.content if getattr(b, "type", None) == "text")


def _complete(provider, prompt):
    """Invia il prompt al provider e restituisce il testo della risposta (può sollevare)."""
    if provider.get("kind") == "anthropic":
        return _anthropic_complete(provider, prompt)
    return _openai_complete(provider, prompt)


def _remote_move(game, state, legal, provider):
    """Mossa scelta dal provider remoto; None se non configurato/errore/non valida."""
    try:
        content = _complete(provider, _build_prompt(game, state, legal))
    except Exception:  # noqa: BLE001 - best effort: in caso di errore si usa il locale
        return None
    if not content:
        return None
    return _match_move(game, legal, content)


def ping(provider):
    """Verifica le credenziali con una chiamata minima. Ritorna (ok, dettaglio)."""
    try:
        content = _complete(provider, "Rispondi solo con: ok")
    except Exception as exc:  # noqa: BLE001 - si riporta l'errore all'utente
        return False, str(exc)
    if not content:
        return False, "Nessuna risposta dal provider"
    return True, content.strip()[:120]


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
