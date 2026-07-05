"""Avversario **IA via API**: la mossa viene chiesta a un modello remoto.

I provider (Qwen, Claude, OpenAI, in prospettiva Gemini/Grok, …) sono configurati dal
super admin nella pagina «Provider IA» (token salvati in DB, non in ``.env``); qui arriva
il dict di configurazione ``provider`` = {code, kind, base_url, model, api_key}:

- kind ``"openai"`` → endpoint OpenAI-compatible chiamato via httpx (Qwen/DashScope,
  OpenAI, e chiunque esponga ``/chat/completions``);
- kind ``"anthropic"`` → SDK ufficiale ``anthropic`` (Claude).

Il modello riceve la scacchiera in testo e l'elenco degli id delle mosse legali, e deve
rispondere con l'id scelto; ``_match_move`` estrae la mossa dalla risposta in modo
tollerante. Ogni errore (rete, timeout, risposta non valida) produce ``None``: chi chiama
ripiega sul giocatore locale (vedi ``opponents.local``), così la partita non si blocca mai.
"""

from __future__ import annotations

import os
import re

import httpx

_SYSTEM_PROMPT = (
    "Sei un giocatore esperto di giochi da tavolo. "
    "Rispondi sempre e solo con l'id esatto della mossa scelta, senza altro testo."
)


def _timeout() -> float:
    """Timeout complessivo (secondi) della chiamata remota; ``AI_TIMEOUT`` nel .env."""
    return float(os.getenv("AI_TIMEOUT", os.getenv("QWEN_TIMEOUT", "10")))


def _http_timeout() -> httpx.Timeout:
    """Timeout con **connect breve**.

    Un endpoint irraggiungibile (es. un indirizzo IPv6 che non risponde e resta in
    SYN_SENT) deve fallire in fretta: le mosse IA girano in un worker, ma accumulare
    connessioni appese degraderebbe comunque il processo. Superato il timeout si
    ripiega sul giocatore locale.
    """
    total = _timeout()
    return httpx.Timeout(total, connect=min(4.0, total))


# ----- Composizione del prompt e parsing della risposta -----
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
    Prima prova i token "a forma di mossa" nel testo, poi cerca gli id per sottostringa
    (dal più lungo, per non confondere ad es. ``e2e4`` con ``e4``).
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


# ----- Client per i due protocolli supportati -----
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
    """Chiamata a Claude tramite l'SDK ufficiale Anthropic (Messages API).

    Nota: sui modelli Claude 4.x non si passa ``temperature``; una risposta con
    ``stop_reason == "refusal"`` equivale a nessuna risposta.
    """
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


# ----- API del modulo -----
def remote_move(game, state, legal, provider):
    """Mossa scelta dal provider remoto; ``None`` se errore o risposta non valida.

    Best effort volutamente silenzioso: qualsiasi problema (rete, quota, refusal,
    risposta non interpretabile) non deve mai interrompere la partita.
    """
    try:
        content = _complete(provider, _build_prompt(game, state, legal))
    except Exception:  # noqa: BLE001 - in caso di errore si usa il giocatore locale
        return None
    if not content:
        return None
    return _match_move(game, legal, content)


def ping(provider):
    """Verifica le credenziali con una chiamata minima. Ritorna (ok, dettaglio).

    Usata dal pulsante «Verifica connessione» della pagina Provider IA.
    """
    try:
        content = _complete(provider, "Rispondi solo con: ok")
    except Exception as exc:  # noqa: BLE001 - si riporta l'errore all'utente
        return False, str(exc)
    if not content:
        return False, "Nessuna risposta dal provider"
    return True, content.strip()[:120]
