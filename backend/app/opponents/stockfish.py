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

Implementazione: per ogni mossa si avvia un processo dedicato (senza stato e
thread-safe: le mosse IA girano su worker in thread separati), si inviano i comandi
UCI e si **attende** la riga ``bestmove`` prima di chiudere con ``quit``.

⚠️ Attenzione a non accodare ``quit`` insieme a ``go``: Stockfish legge stdin anche
durante la ricerca e un ``quit`` ricevuto mentre pensa la **interrompe subito**
(bestmove a profondità ~1 → gioco debolissimo qualunque sia il movetime). È stato un
bug reale di questa integrazione. Un watchdog uccide il processo se non risponde.

I **livelli preconfigurati** (``PRESETS``) mappano nomi di divinità greche su
combinazioni di Elo simulato e tempo per mossa, selezionabili al setup della partita;
il percorso del binario resta quello globale (``stockfish.path``/env/PATH).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading

from .. import settings_service

# Margine (secondi) oltre il movetime prima di uccidere il processo: copre avvio,
# caricamento della rete NNUE e latenza di I/O.
_STARTUP_GRACE = 8.0

# Livelli preconfigurati dell'avversario Stockfish, dal più forte al più debole.
# elo=0 → nessun limite (piena forza NNUE); altrimenti UCI_LimitStrength + UCI_Elo
# (range accettato ~1320-3190): è il modo più fedele di simulare un giocatore umano.
PRESETS: dict[str, dict] = {
    "zeus": {"label": "Zeus (Extreme)", "elo": 0, "skill_level": 20, "move_ms": 4000},
    "atena": {"label": "Atena (Master)", "elo": 2700, "skill_level": 20, "move_ms": 2500},
    "apollo": {"label": "Apollo (Champion)", "elo": 2350, "skill_level": 20, "move_ms": 1800},
    "ares": {"label": "Ares (Expert)", "elo": 2000, "skill_level": 20, "move_ms": 1200},
    "hermes": {"label": "Hermes (Middle)", "elo": 1700, "skill_level": 20, "move_ms": 800},
    "pan": {"label": "Pan (Learner)", "elo": 1400, "skill_level": 20, "move_ms": 500},
}


def preset_label(level: str | None) -> str | None:
    """Etichetta leggibile del livello (es. «Zeus (Extreme)»); None se sconosciuto."""
    preset = PRESETS.get(level or "")
    return preset["label"] if preset else None


def config_for_level(base_cfg: dict, level: str | None) -> dict:
    """Configurazione effettiva per una partita: preset del livello sopra la base.

    ``base_cfg`` è la configurazione globale (percorso binario + valori del super
    admin); se ``level`` è un preset noto, Elo/skill/movetime vengono sovrascritti.
    Senza livello (o livello ignoto) valgono i parametri globali.
    """
    preset = PRESETS.get(level or "")
    if not preset:
        return base_cfg
    merged = dict(base_cfg)
    merged.update({k: preset[k] for k in ("elo", "skill_level", "move_ms")})
    return merged


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


def _uci_dialogue(path: str, commands: list[str], timeout_s: float):
    """Esegue un dialogo UCI e ritorna le righe di output **fino a** ``bestmove``.

    I comandi (che devono terminare con un ``go …``) vengono inviati subito; poi si
    LEGGE l'output riga per riga finché arriva ``bestmove`` — solo a quel punto si
    manda ``quit``. Inviare ``quit`` insieme a ``go`` interromperebbe la ricerca
    (vedi nota nel docstring del modulo). Un watchdog uccide il processo se non
    risponde entro ``timeout_s``. Ritorna ``None`` in caso di errore.
    """
    try:
        proc = subprocess.Popen(
            [path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return None  # binario mancante o non eseguibile

    watchdog = threading.Timer(timeout_s, proc.kill)
    watchdog.start()
    lines: list[str] = []
    try:
        proc.stdin.write("\n".join(commands) + "\n")
        proc.stdin.flush()
        for line in proc.stdout:  # se il watchdog uccide il processo, il flusso termina
            lines.append(line.rstrip())
            if line.startswith("bestmove"):
                break
        else:
            return None  # output finito senza bestmove (processo ucciso o non-UCI)
    except (OSError, ValueError):
        return None
    finally:
        watchdog.cancel()
        try:
            proc.stdin.write("quit\n")
            proc.stdin.flush()
        except (OSError, ValueError):
            pass  # il processo può essere già uscito (es. finto motore nei test)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
    return lines


def _strength_commands(cfg: dict) -> list[str]:
    """Comandi ``setoption`` per la forza richiesta (Skill Level / Elo simulato)."""
    commands = []
    skill = int(cfg.get("skill_level", 20))
    if 0 <= skill < 20:  # 20 è il default del motore: si imposta solo se ridotto
        commands.append(f"setoption name Skill Level value {skill}")
    elo = int(cfg.get("elo") or 0)
    if elo > 0:
        commands.append("setoption name UCI_LimitStrength value true")
        commands.append(f"setoption name UCI_Elo value {max(1320, min(3190, elo))}")
    return commands


def verify(cfg: dict):
    """Diagnostica per il super admin: il binario risponde al protocollo UCI?

    Ritorna ``(ok, dettaglio)``: in caso di successo il dettaglio riporta il nome che
    il motore dichiara (es. «Stockfish 18») e la mossa proposta dalla posizione
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

    commands = ["uci", "ucinewgame", "position startpos", "go movetime 500"]
    lines = _uci_dialogue(path, commands, timeout_s=15)
    if lines is None:
        return False, "Esecuzione fallita o binario che non risponde"

    name = None
    bestmove = None
    for line in lines:
        if line.startswith("id name "):
            name = line[len("id name ") :].strip()
        elif line.startswith("bestmove"):
            parts = line.split()
            bestmove = parts[1] if len(parts) >= 2 else None
    if not bestmove:
        return False, "Il binario non risponde al protocollo UCI (nessun bestmove)"
    return True, f"{name or 'motore UCI'} — mossa di prova dalla posizione iniziale: {bestmove}"


def _ask_bestmove(cfg: dict, position: str) -> str | None:
    """Mossa per la posizione data: opzioni di forza → posizione → ``go movetime``."""
    move_ms = max(50, int(cfg.get("move_ms") or 1000))
    commands = ["uci", *_strength_commands(cfg), "ucinewgame", position, f"go movetime {move_ms}"]
    lines = _uci_dialogue(cfg["path"], commands, timeout_s=move_ms / 1000.0 + _STARTUP_GRACE)
    if not lines:
        return None
    for line in reversed(lines):
        if line.startswith("bestmove"):
            parts = line.split()
            if len(parts) >= 2 and parts[1] not in ("(none)", "0000"):
                return parts[1]
            return None
    return None
