"""Avversari non umani: dispatch per tipo, con ripiego sul giocatore locale.

Un lato di una partita può essere di **tre tipi**:

- ``"human"`` — un giocatore umano (gestito dagli endpoint, non da questo pacchetto);
- ``"stockfish"`` — il motore **Stockfish** (NNUE) via protocollo UCI, configurabile
  (percorso binario, Elo/Skill Level, tempo per mossa) → ``stockfish.py``;
- ``"ai"`` — un'**IA via API** (Qwen, Claude, e in prospettiva Gemini/Grok, …): la mossa
  viene chiesta al provider remoto attivo → ``api_ai.py``.

Per entrambi i tipi non umani, se l'avversario scelto non può muovere (binario di
Stockfish assente, nessun provider configurato, errore di rete, risposta non valida) la
mossa passa al **giocatore locale** (``local.py``: motore alpha-beta dedicato per gli
scacchi, minimax generico per gli altri giochi), così la partita non si blocca mai.
Il campo ``sorgente`` restituito dice chi ha davvero giocato.
"""

from __future__ import annotations

from . import api_ai, local, stockfish

__all__ = ["choose_move", "api_ai", "local", "stockfish"]


def choose_move(
    game,
    state,
    history=None,
    kind="ai",
    provider=None,
    stockfish_cfg=None,
    think_ms=None,
    jitter=0,
    style=None,
    tt=None,
    start_fen=None,
):
    """Sceglie una mossa legale per il lato IA di tipo ``kind``. Ritorna (mossa, sorgente).

    ``sorgente`` ∈ {"book", "stockfish", <codice provider>, "engine", "local"}.
    Parametri: ``provider`` è la configurazione del provider API attivo (o None);
    ``stockfish_cfg`` quella di Stockfish; ``think_ms``/``jitter``/``style`` riguardano
    il giocatore locale (budget di tempo, varietà tra partite, profilo avversario).
    """
    legal = list(game.legal_moves(state))
    if not legal:
        raise ValueError("Nessuna mossa legale disponibile")

    # Libro delle aperture per ogni tipo di IA: risposte istantanee e varie in apertura
    # (per gli scacchi è indicizzato per posizione, quindi copre anche le trasposizioni).
    # APERTURA-BERSAGLIO: se lo stile porta le aperture più deboli del profilo
    # avversario, il libro preferisce le linee che ci finiscono dentro.
    if history is not None:
        prefer = (style or {}).get("target_openings") or None
        book = game.opening_move(state, history, prefer=prefer)
        if book is not None and book in legal:
            return book, "book"

    if kind == "stockfish":
        move = stockfish.best_move(game, state, history, stockfish_cfg, start_fen=start_fen)
        if move is not None and move in legal:
            return move, "stockfish"
    elif provider:  # kind "ai": l'avversario è il modello remoto scelto dal super admin
        move = api_ai.remote_move(game, state, legal, provider)
        if move is not None and move in legal:
            return move, provider.get("code") or "remote"

    # Ripiego (o gioco diretto quando non c'è nulla di configurato): giocatore locale.
    return local.best_move(
        game, state, legal, history=history, think_ms=think_ms, jitter=jitter, style=style, tt=tt
    )
