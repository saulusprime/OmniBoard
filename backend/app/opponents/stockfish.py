"""Avversario **Stockfish** (motore UCI con valutazione neurale NNUE), configurabile.

Richiede il binario di Stockfish installato sul server (``brew install stockfish``,
``apt install stockfish``, o download da stockfishchess.org). Il percorso si configura
dal super admin (parametro ``stockfish.path``) oppure con la variabile d'ambiente
``STOCKFISH_PATH``; in mancanza si cerca ``stockfish`` nel PATH. Se il binario non c'è
o fallisce, chi chiama ripiega sul giocatore locale: la partita non si blocca mai.

Forza regolabile dal super admin:
- ``stockfish.skill_level`` (0-20, 20 = piena forza): l'opzione UCI *Skill Level*;
- ``stockfish.elo`` (0 = disattivo): se > 0 attiva *UCI_LimitStrength* + *UCI_Elo*
  (Stockfish accetta circa 1320-3190) — il modo più fedele di simulare un umano;
- ``stockfish.move_ms``: tempo di riflessione per mossa (``go movetime``).

Implementazione volutamente **one-shot**: per ogni mossa si avvia un processo, si
inviano tutti i comandi UCI in un colpo solo (chiusi da ``quit``) e si legge l'output
fino a ``bestmove``. Costa ~100ms di avvio a mossa ma è senza stato e thread-safe
(le mosse IA girano su worker in thread separati); un processo persistente con lock è
un'ottimizzazione futura annotata in TODO.md.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from .. import settings_service

# Margine (secondi) oltre il movetime prima di uccidere il processo: copre avvio,
# caricamento della rete NNUE e latenza di I/O.
_STARTUP_GRACE = 8.0


def get_config(db) -> dict:
    """Configurazione Stockfish dai parametri super admin (con fallback da ambiente)."""
    path = (
        settings_service.get(db, "stockfish.path")
        or os.getenv("STOCKFISH_PATH")
        or shutil.which("stockfish")
        or ""
    )
    return {
        "path": path,
        "move_ms": int(settings_service.get(db, "stockfish.move_ms")),
        "elo": int(settings_service.get(db, "stockfish.elo")),
        "skill_level": int(settings_service.get(db, "stockfish.skill_level")),
    }


def is_available(cfg: dict) -> bool:
    """True se il binario configurato esiste ed è eseguibile."""
    path = (cfg or {}).get("path") or ""
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def best_move(game, state, history, cfg):
    """Mossa scelta da Stockfish; ``None`` se non disponibile o in errore.

    Funziona solo per gli scacchi (protocollo UCI); per gli altri giochi ritorna
    subito ``None`` e chi chiama usa il giocatore locale. La posizione è trasmessa
    come ``startpos + moves`` quando lo storico è disponibile (dà al motore anche il
    contesto per le ripetizioni), altrimenti come FEN.
    """
    if getattr(game, "code", "") != "chess" or not is_available(cfg):
        return None

    if history:
        position = f"position startpos moves {' '.join(history)}"
    else:
        position = f"position fen {game.to_fen(state)}"

    uci = _ask_bestmove(cfg, position)
    if not uci:
        return None
    # Traduzione dell'uci in una mossa del motore interno, validata tra le legali.
    for move in game.legal_moves(state):
        if game.move_id(move) == uci:
            return move
    return None


def verify(cfg: dict):
    """Diagnostica per il super admin: il binario risponde al protocollo UCI?

    Ritorna ``(ok, dettaglio)``: in caso di successo il dettaglio riporta il nome che
    il motore dichiara (es. «Stockfish 17») e la mossa proposta dalla posizione
    iniziale; altrimenti il motivo del fallimento. Nessuna eccezione esce da qui.
    """
    path = (cfg or {}).get("path") or ""
    if not path:
        return False, (
            "Nessun binario configurato: imposta stockfish.path, la variabile "
            "STOCKFISH_PATH, oppure installa 'stockfish' nel PATH."
        )
    if not is_available(cfg):
        return False, f"Binario non trovato o non eseguibile: {path}"
    try:
        result = subprocess.run(
            [path],
            input="uci\nucinewgame\nposition startpos\ngo movetime 100\nquit\n",
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Esecuzione fallita: {exc}"

    name = None
    bestmove = None
    for line in result.stdout.splitlines():
        if line.startswith("id name "):
            name = line[len("id name ") :].strip()
        elif line.startswith("bestmove"):
            parts = line.split()
            bestmove = parts[1] if len(parts) >= 2 else None
    if not bestmove:
        return False, "Il binario non risponde al protocollo UCI (nessun bestmove)"
    return True, f"{name or 'motore UCI'} — mossa di prova dalla posizione iniziale: {bestmove}"


def _ask_bestmove(cfg: dict, position: str) -> str | None:
    """Dialogo UCI one-shot: opzioni → posizione → ``go movetime`` → ``bestmove``."""
    move_ms = max(50, int(cfg.get("move_ms") or 1000))
    commands = ["uci"]
    skill = int(cfg.get("skill_level", 20))
    if 0 <= skill < 20:  # 20 è il default del motore: si imposta solo se ridotto
        commands.append(f"setoption name Skill Level value {skill}")
    elo = int(cfg.get("elo") or 0)
    if elo > 0:
        commands.append("setoption name UCI_LimitStrength value true")
        commands.append(f"setoption name UCI_Elo value {max(1320, min(3190, elo))}")
    commands += ["ucinewgame", position, f"go movetime {move_ms}", "quit"]

    try:
        result = subprocess.run(
            [cfg["path"]],
            input="\n".join(commands) + "\n",
            capture_output=True,
            text=True,
            timeout=move_ms / 1000.0 + _STARTUP_GRACE,
        )
    except (OSError, subprocess.SubprocessError):
        return None  # binario mancante/non eseguibile/appeso: si ripiega sul locale

    # L'ultima riga utile è "bestmove <uci> [ponder ...]".
    for line in reversed(result.stdout.splitlines()):
        if line.startswith("bestmove"):
            parts = line.split()
            if len(parts) >= 2 and parts[1] not in ("(none)", "0000"):
                return parts[1]
            return None
    return None
