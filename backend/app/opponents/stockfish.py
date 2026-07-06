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

Implementazione: un **processo PERSISTENTE** (singleton di modulo, protetto da lock:
le mosse IA girano su worker in thread separati e le ricerche vengono serializzate).
Rispetto all'avvio one-shot per mossa si risparmiano ~100 ms di avvio + caricamento
della rete NNUE a ogni mossa, e le hash table restano calde lungo la partita:

- l'handshake ``uci``/``uciok`` avviene una volta sola, allo spawn;
- le opzioni di forza vengono inviate solo quando CAMBIANO (in IA-vs-IA i due lati
  possono avere preset diversi: il diff le riallinea a ogni alternanza);
- ``ucinewgame`` parte solo quando la posizione NON è la continuazione della
  precedente (partita nuova): nelle continuazioni il motore riusa le hash;
- un watchdog per ricerca uccide il processo se non risponde; alla richiesta
  successiva il motore viene **rilanciato da solo** (respawn), e una pipe rotta
  prima della ricerca viene ritentata una volta. In ogni caso di errore si ritorna
  ``None`` e chi chiama ripiega sul giocatore locale.

⚠️ Attenzione a non accodare ``quit`` insieme a ``go``: Stockfish legge stdin anche
durante la ricerca e un ``quit`` ricevuto mentre pensa la **interrompe subito**
(bestmove a profondità ~1 → gioco debolissimo qualunque sia il movetime). È stato un
bug reale di questa integrazione. Il ``quit`` ora si manda solo alla chiusura del
processo persistente (shutdown/respawn), mai durante il gioco.

I **livelli preconfigurati** (``PRESETS``) mappano nomi di divinità greche su
combinazioni di Elo simulato e tempo per mossa, selezionabili al setup della partita;
il percorso del binario resta quello globale (``stockfish.path``/env/PATH).
"""

from __future__ import annotations

import atexit
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

    # Le opzioni di forza (preset per lato) e il movetime viaggiano nella cfg:
    # il processo persistente riallinea solo ciò che è cambiato.
    uci = _ENGINE.bestmove(cfg, position)
    if not uci:
        return None
    # Traduzione dell'uci in una mossa del motore interno, validata tra le legali.
    for move in game.legal_moves(state):
        if game.move_id(move) == uci:
            return move
    return None


class _PersistentEngine:
    """Il processo Stockfish persistente: uno per tutto il backend, con lock.

    Il lock serializza le ricerche (una alla volta: la CPU è comunque il collo
    di bottiglia e il protocollo UCI non è concorrente); lo stato ricordato tra
    una mossa e l'altra — opzioni correnti e ultima posizione — permette di
    inviare solo i comandi davvero necessari.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._path: str | None = None
        self._name: str | None = None
        self._opts: dict[str, str] = {}  # opzioni UCI già impostate sul processo
        self._last_position: str | None = None
        self._searches = 0  # ricerche servite dal processo corrente (diagnostica)

    # ----- gestione del processo -----
    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _close(self) -> None:
        """Chiude il processo (quit gentile, kill se non collabora) e azzera lo stato."""
        proc, self._proc = self._proc, None
        self._opts = {}
        self._last_position = None
        self._searches = 0
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.stdin.write("quit\n")
                proc.stdin.flush()
                proc.wait(timeout=2)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            proc.kill()

    def _spawn(self, path: str) -> bool:
        """Avvia il binario e completa l'handshake ``uci`` → ``uciok``."""
        self._close()
        try:
            self._proc = subprocess.Popen(
                [path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self._path = path
            self._send("uci")
        except OSError:
            self._proc = None
            return False
        lines = self._read_until("uciok", timeout_s=_STARTUP_GRACE)
        if lines is None:
            self._close()
            return False
        self._name = next(
            (ln[len("id name ") :].strip() for ln in lines if ln.startswith("id name ")), None
        )
        return True

    def _send(self, command: str) -> None:
        self._proc.stdin.write(command + "\n")
        self._proc.stdin.flush()

    def _read_until(self, prefix: str, timeout_s: float):
        """Legge righe fino a quella che inizia con ``prefix`` (watchdog sul totale).

        Ritorna le righe lette, oppure ``None`` su timeout/EOF (il watchdog uccide
        il processo: la richiesta successiva farà il respawn).
        """
        watchdog = threading.Timer(timeout_s, self._proc.kill)
        watchdog.start()
        lines: list[str] = []
        try:
            while True:
                line = self._proc.stdout.readline()
                if not line:
                    return None  # EOF: processo morto o ucciso dal watchdog
                line = line.rstrip()
                lines.append(line)
                if line.startswith(prefix):
                    return lines
        except (OSError, ValueError):
            return None
        finally:
            watchdog.cancel()

    # ----- protocollo di gioco -----
    def _apply_strength(self, cfg: dict) -> None:
        """Allinea le opzioni di forza, inviando SOLO quelle diverse dallo stato attuale.

        A differenza del vecchio one-shot, il processo vive tra una mossa e l'altra:
        i valori vanno anche RIPRISTINATI (es. da Pan/1400 Elo a Zeus/piena forza),
        per questo LimitStrength viene sempre dichiarato esplicitamente.
        """
        desired = {"Skill Level": str(max(0, min(20, int(cfg.get("skill_level", 20)))))}
        elo = int(cfg.get("elo") or 0)
        if elo > 0:
            desired["UCI_LimitStrength"] = "true"
            desired["UCI_Elo"] = str(max(1320, min(3190, elo)))
        else:
            desired["UCI_LimitStrength"] = "false"
        for name, value in desired.items():
            if self._opts.get(name) != value:
                self._send(f"setoption name {name} value {value}")
                self._opts[name] = value

    def bestmove(self, cfg: dict, position: str) -> str | None:
        """Mossa migliore per la posizione, riusando il processo persistente."""
        with self._lock:
            for _attempt in range(2):  # un solo respawn di recupero su pipe rotta
                if not self._alive() or self._path != cfg["path"]:
                    if not self._spawn(cfg["path"]):
                        return None
                move_ms = max(50, int(cfg.get("move_ms") or 1000))
                try:
                    self._apply_strength(cfg)
                    if not (self._last_position and position.startswith(self._last_position)):
                        # Partita nuova (non è la continuazione della precedente):
                        # si azzerano le hash; nelle continuazioni restano calde.
                        self._send("ucinewgame")
                        self._last_position = None
                    self._send(position)
                    self._send(f"go movetime {move_ms}")
                except (OSError, ValueError):
                    self._close()
                    continue  # pipe rotta PRIMA della ricerca: respawn e riprova
                lines = self._read_until("bestmove", move_ms / 1000.0 + _STARTUP_GRACE)
                if lines is None:
                    self._close()  # timeout in ricerca: niente retry (budget già speso)
                    return None
                self._last_position = position
                self._searches += 1
                parts = lines[-1].split()
                if len(parts) >= 2 and parts[1] not in ("(none)", "0000"):
                    return parts[1]
                return None
            return None

    def evaluate(self, cfg: dict, position: str) -> dict | None:
        """Valutazione della posizione: {cp | mate (dal punto di vista di chi muove), best}.

        Riusa il flusso di ricerca del processo persistente ma conserva le righe
        ``info … score …`` (l'ultima è quella alla profondità massima raggiunta).
        Usata dall'analisi post-partita; ``None`` in caso di errore.
        """
        with self._lock:
            for _attempt in range(2):
                if not self._alive() or self._path != cfg["path"]:
                    if not self._spawn(cfg["path"]):
                        return None
                move_ms = max(50, int(cfg.get("move_ms") or 200))
                try:
                    self._apply_strength(cfg)
                    if not (self._last_position and position.startswith(self._last_position)):
                        self._send("ucinewgame")
                    self._send(position)
                    self._send(f"go movetime {move_ms}")
                except (OSError, ValueError):
                    self._close()
                    continue
                lines = self._read_until("bestmove", move_ms / 1000.0 + _STARTUP_GRACE)
                if lines is None:
                    self._close()
                    return None
                self._last_position = position
                self._searches += 1
                cp = mate = None
                for line in lines:  # l'ultima "score" vince (profondità maggiore)
                    if line.startswith("info ") and " score " in line:
                        parts = line.split()
                        i = parts.index("score")
                        if parts[i + 1] == "cp":
                            cp, mate = int(parts[i + 2]), None
                        elif parts[i + 1] == "mate":
                            cp, mate = None, int(parts[i + 2])
                best = lines[-1].split()
                best_uci = best[1] if len(best) >= 2 and best[1] not in ("(none)", "0000") else None
                return {"cp": cp, "mate": mate, "best": best_uci}
            return None

    def stats(self) -> dict | None:
        """PID e ricerche servite dal processo corrente (per la diagnostica admin)."""
        if not self._alive():
            return None
        return {"pid": self._proc.pid, "name": self._name, "searches": self._searches}

    def shutdown(self) -> None:
        with self._lock:
            self._close()


_ENGINE = _PersistentEngine()
atexit.register(_ENGINE.shutdown)  # quit gentile alla chiusura del backend


def shutdown() -> None:
    """Chiude il processo persistente (riavvii puliti e isolamento nei test)."""
    _ENGINE.shutdown()


def _uci_dialogue(path: str, commands: list[str], timeout_s: float):
    """Esegue un dialogo UCI **one-shot** e ritorna le righe fino a ``bestmove``.

    Usato SOLO dalla diagnostica :func:`verify` (il gioco passa dal processo
    persistente): un processo dedicato isola il test del binario dallo stato
    del motore in servizio.

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
    detail = f"{name or 'motore UCI'} — mossa di prova dalla posizione iniziale: {bestmove}"
    stats = _ENGINE.stats()
    if stats:
        detail += (
            f" · processo persistente attivo (PID {stats['pid']}, "
            f"{stats['searches']} ricerche servite)"
        )
    return True, detail
