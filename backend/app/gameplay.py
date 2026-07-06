"""Svolgimento delle partite: logica condivisa tra gli endpoint e il worker IA.

La mossa dell'IA **non** viene più calcolata dentro la richiesta HTTP: ``schedule_ai``
la affida a un thread in background (al massimo uno per sessione) e il client si
aggiorna facendo polling dello stato. Così una mossa del motore (anche 2s) o un'intera
partita IA-vs-IA non bloccano mai una risposta.

Con il parametro ``ai.async_moves`` disattivato — o con la variabile d'ambiente
``AI_ASYNC=0``, usata nei test — il calcolo torna in linea, sincrono, come in origine.

Nota: lo scheduling è in-process (un solo worker uvicorn). Passando a più processi va
sostituito con una coda di lavoro vera (vedi TODO.md).
"""

from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from engine import get_game

from . import ai_providers, chess_profile, models, opponents, services, settings_service
from .database import SessionLocal
from .opponents import stockfish

logger = logging.getLogger(__name__)

_running_lock = threading.Lock()
_running: set[int] = set()


# ----- Stato e log mosse -----
def load_state(game, session: models.GameSession):
    return game.deserialize_state(json.loads(session.state_json))


def save_state(game, session: models.GameSession, state) -> None:
    session.state_json = json.dumps(game.serialize_state(state))


def side_is_ai(session: models.GameSession, player: int) -> bool:
    return session.x_is_ai if player == 0 else session.o_is_ai


def side_kind(session: models.GameSession, player: int) -> str:
    """Tipo del lato: "human", "ai" (IA via API) o "stockfish".

    Le righe storiche (create prima dell'introduzione dei tipi) hanno ``*_ai_kind``
    None con ``*_is_ai`` True: si assume "ai", il comportamento di allora.
    """
    if player == 0:
        return (session.x_ai_kind or "ai") if session.x_is_ai else "human"
    return (session.o_ai_kind or "ai") if session.o_is_ai else "human"


def side_level(session: models.GameSession, player: int) -> str | None:
    """Livello preconfigurato del lato Stockfish (chiave di ``stockfish.PRESETS``)."""
    return session.x_ai_level if player == 0 else session.o_ai_level


def side_provider(session: models.GameSession, player: int) -> str | None:
    """Concorrente IA scelto per il lato ("gemini", "anthropic", …); None = attivo."""
    return session.x_ai_provider if player == 0 else session.o_ai_provider


def record_move(game, state_before, move, player: int, moves: list) -> None:
    moves.append(
        {
            "ply": len(moves) + 1,
            "player": "X" if player == 0 else "O",
            "notation": game.describe_move(state_before, move),
            "id": game.move_id(move),
        }
    )


def history_ids(moves: list) -> list:
    return [m["id"] for m in moves if "id" in m]


def finish_if_terminal(db: Session, game, session: models.GameSession, state) -> None:
    if session.status == "finished":
        return
    if game.is_terminal(state):
        winner = game.outcome(state).winner
        session.winner = "draw" if winner is None else ("x" if winner == 0 else "o")
    elif game.is_repetition_draw(history_ids(json.loads(session.moves_json or "[]"))):
        # Patta per TRIPLICE RIPETIZIONE, dichiarata d'ufficio dall'arbitro (il
        # server) alla terza occorrenza della stessa posizione: negli scacchi da
        # regolamento è su richiesta, ma qui evita le partite infinite.
        session.winner = "draw"
        session.finish_reason = "repetition"
    else:
        return
    session.status = "finished"
    services.finalize_session(db, session)
    db.commit()


def opponent_style(db: Session, game, session: models.GameSession):
    """Stile di gioco dell'IA derivato dal profilo dell'avversario umano (solo scacchi).

    Restituisce ``{'aggression':, 'contempt':, 'target_openings': [...]}`` o ``None``
    (gioco neutro) se non c'è un
    avversario umano identificabile o il gioco non ha un profilo dedicato.
    """
    if game.code != chess_profile.CHESS_CODE:
        return None
    if session.x_is_ai and not session.o_is_ai and session.o_user_id:
        opponent_id = session.o_user_id
    elif session.o_is_ai and not session.x_is_ai and session.x_user_id:
        opponent_id = session.x_user_id
    else:
        return None
    profile = chess_profile.build_profile(db, opponent_id)
    if not profile:
        return None
    style = dict(profile["style"])
    # Aperture-bersaglio: le linee in cui l'avversario storicamente rende peggio.
    # Il libro le preferirà quando la posizione lo consente (vedi opponents/__init__).
    style["target_openings"] = profile.get("weakest_openings") or []
    return style


# ----- Orologio di gioco (solo scacchi) -----
# Categorie e vincoli (minuti a testa): blitz <15, rapid 15-60, classical >60.
# Il formato FIDE ufficiale ha parametri fissi: 90 minuti + 30 secondi a mossa fin
# dall'inizio, e ulteriori 30 minuti dopo la 40ª mossa del giocatore.
_TIME_CATEGORIES = {
    "blitz": {"min": 1, "max": 14, "default": 5},
    "rapid": {"min": 15, "max": 60, "default": 25},
    "classical": {"min": 61, "max": 600, "default": 90},
}
_FIDE_BASE_S = 90 * 60
_FIDE_INC_S = 30
_FIDE_EXTRA_MS = 30 * 60 * 1000  # bonus dopo la 40ª mossa del giocatore
_FIDE_EXTRA_AT_MOVE = 40


def _now() -> datetime:
    """Orologio del server in UTC naive (coerente con i DateTime persistiti).

    Centralizzato così i test possono simulare il passare del tempo con monkeypatch.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def build_time_control(game_code: str, category, base_min, inc_s: int):
    """Valida la richiesta di orologio e la normalizza in ``{category, base_s, inc_s}``.

    Ritorna ``None`` se non è richiesto alcun orologio; solleva ``ValueError`` (con
    messaggio per l'utente) se i parametri non rispettano le regole delle categorie.
    """
    if not category:
        return None
    if game_code != "chess":
        raise ValueError("L'orologio di gioco è disponibile solo per gli scacchi")
    if category == "fide":
        # Formato ufficiale: parametri fissi, niente personalizzazioni.
        if base_min is not None:
            raise ValueError("Il formato FIDE ha un tempo fisso (90′): non impostare i minuti")
        if inc_s:
            raise ValueError("Il formato FIDE ha già il suo incremento (30″): non impostarlo")
        return {"category": "fide", "base_s": _FIDE_BASE_S, "inc_s": _FIDE_INC_S}
    rules = _TIME_CATEGORIES.get(category)
    if not rules:
        raise ValueError("Categoria di tempo sconosciuta (blitz, rapid, classical, fide)")
    base = rules["default"] if base_min is None else int(base_min)
    if not rules["min"] <= base <= rules["max"]:
        raise ValueError(
            f"Per la categoria {category} i minuti a testa devono essere tra "
            f"{rules['min']} e {rules['max']}"
        )
    if not 0 <= int(inc_s) <= 60:
        raise ValueError("L'incremento Fischer deve essere tra 0 e 60 secondi")
    return {"category": category, "base_s": base * 60, "inc_s": int(inc_s)}


def init_clock(session: models.GameSession, tc) -> None:
    """Imposta l'orologio su una sessione appena creata (l'orologio di X parte)."""
    if not tc:
        return
    session.tc_category = tc["category"]
    session.tc_base_s = tc["base_s"]
    session.tc_inc_s = tc["inc_s"]
    session.x_clock_ms = tc["base_s"] * 1000
    session.o_clock_ms = tc["base_s"] * 1000
    session.turn_started_at = _now()


def _bonus_ms(category: str, inc_s: int, move_number: int) -> int:
    """Millisecondi accreditati DOPO una mossa completata.

    Fischer: ``inc_s`` fissi a mossa. FIDE: 30″ a mossa fin dall'inizio, più i 30
    minuti aggiuntivi quando il giocatore completa la sua 40ª mossa.
    """
    bonus = inc_s * 1000
    if category == "fide" and move_number == _FIDE_EXTRA_AT_MOVE:
        bonus += _FIDE_EXTRA_MS
    return bonus


def _remaining_ms(session: models.GameSession, player: int) -> int:
    """Tempo residuo *vivo* del giocatore (scala mentre è il suo turno)."""
    stored = session.x_clock_ms if player == 0 else session.o_clock_ms
    if session.turn_started_at is None:
        return stored
    elapsed = int((_now() - session.turn_started_at).total_seconds() * 1000)
    return stored - elapsed


def _winner_on_time(game, state, flagged_player: int) -> str:
    """Esito alla caduta della bandierina: vince l'avversario, MA è patta se questi
    non ha più materiale per dare matto. Semplificazione (regola FIDE completa: "non
    può dare matto con alcuna serie di mosse legali"): patta solo con il re nudo."""
    opponent_pieces = [
        p
        for p in state.board
        if p and (p.isupper() if flagged_player == 1 else p.islower()) and p.upper() != "K"
    ]
    if not opponent_pieces:
        return "draw"
    return "o" if flagged_player == 0 else "x"


def _finish_on_time(db: Session, game, session: models.GameSession, flagged_player: int) -> None:
    """Chiude la partita per tempo scaduto e aggiorna i punteggi."""
    state = load_state(game, session)
    side = "x" if flagged_player == 0 else "o"
    session.winner = _winner_on_time(game, state, flagged_player)
    session.status = "finished"
    session.finish_reason = "time"
    if flagged_player == 0:
        session.x_clock_ms = 0
    else:
        session.o_clock_ms = 0
    services.finalize_session(db, session)
    db.commit()
    logger.info("Sessione %s conclusa per tempo: bandierina di %s", session.id, side)


def check_time(db: Session, game, session: models.GameSession) -> None:
    """Controllo pigro della bandierina: chiude la partita se il tempo del giocatore
    al tratto è esaurito. Chiamato dalle letture di stato (polling) e prima delle
    mosse: l'orologio è autorevole anche se nessuno muove più."""
    if session.status != "in_progress" or not session.tc_category:
        return
    state = load_state(game, session)
    player = game.current_player(state)
    if _remaining_ms(session, player) <= 0:
        _finish_on_time(db, game, session, player)


def consume_time(db: Session, game, session: models.GameSession, player: int, moves: list):
    """Scala il tempo pensato dal giocatore che ha appena mosso e accredita il bonus.

    ``moves`` è il log PRIMA della mossa (serve per il numero di mossa del giocatore,
    usato dal bonus FIDE della 40ª). Ritorna False — chiudendo la partita per tempo —
    se il giocatore ha superato il residuo mentre pensava; True altrimenti.
    """
    if not session.tc_category:
        return True
    remaining = _remaining_ms(session, player)
    if remaining <= 0:
        _finish_on_time(db, game, session, player)
        return False
    move_number = len(moves) // 2 + 1  # la mossa n° del giocatore che sta muovendo
    remaining += _bonus_ms(session.tc_category, session.tc_inc_s or 0, move_number)
    if player == 0:
        session.x_clock_ms = remaining
    else:
        session.o_clock_ms = remaining
    session.turn_started_at = _now()  # parte l'orologio dell'avversario
    return True


def clock_view(session: models.GameSession, game) -> dict | None:
    """Stato dell'orologio per il client: residui *vivi* e lato in movimento."""
    if not session.tc_category:
        return None
    running = None
    x_ms, o_ms = session.x_clock_ms, session.o_clock_ms
    if session.status == "in_progress":
        state = load_state(game, session)
        player = game.current_player(state)
        running = "x" if player == 0 else "o"
        live = max(0, _remaining_ms(session, player))
        if player == 0:
            x_ms = live
        else:
            o_ms = live
    return {
        "category": session.tc_category,
        "base_s": session.tc_base_s,
        "inc_s": session.tc_inc_s,
        "x_ms": max(0, x_ms),
        "o_ms": max(0, o_ms),
        "running": running,
    }


# ----- Nodi del caso: il SERVER tira i dadi (giochi stocastici, es. backgammon) -----
def resolve_chance(db: Session, game, session: models.GameSession) -> bool:
    """Se lo stato è un nodo del caso, estrae e applica gli eventi aleatori.

    Il tiro è del **server** (arbitro): nessun client può scegliere o rigiocare i
    dadi. Ogni tiro viene registrato nel log della partita (es. «🎲 5-3»); se il
    tiro non è giocabile il turno passa da solo e si continua a tirare per l'altro
    giocatore, finché qualcuno può muovere o la partita finisce. Ritorna True se
    lo stato è cambiato (chi chiama deve ricaricare stato e log).

    Chiamata dalle letture di stato (pigra, come la bandierina dell'orologio),
    prima delle mosse umane e nel ciclo del worker IA: chiunque "tocchi" la
    partita materializza il tiro mancante.
    """
    if session.status != "in_progress" or not game.is_stochastic:
        return False
    state = load_state(game, session)
    if not game.is_chance_node(state):
        return False
    moves = json.loads(session.moves_json or "[]")
    guard = 0
    while game.is_chance_node(state) and guard < 8:
        guard += 1  # difesa da loop teorici: 8 passaggi consecutivi non esistono in pratica
        outcomes = game.chance_outcomes(state)
        events = [e for e, _p in outcomes]
        weights = [p for _e, p in outcomes]
        event = random.choices(events, weights=weights, k=1)[0]
        roller = game.current_player(state)
        state = game.apply_chance(state, event)
        notation = game.describe_chance(event)
        if game.current_player(state) != roller and not game.is_terminal(state):
            notation += " — nessuna mossa possibile, il turno passa"
        moves.append(
            {
                "ply": len(moves) + 1,
                "player": "X" if roller == 0 else "O",
                "notation": notation,
                # niente "id": i tiri non sono mosse (restano fuori dallo storico UCI)
            }
        )
    session.moves_json = json.dumps(moves)
    save_state(game, session, state)
    db.commit()
    return True


# ----- Avanzamento IA -----
def _watch_pace_ms(db: Session) -> int:
    """Ritmo minimo (ms) tra le mosse IA "osservate" dal client.

    Le mosse di libro sono istantanee: senza un ritmo minimo una partita IA-vs-IA
    giocherebbe mezza apertura prima ancora che il browser disegni la scacchiera, e il
    polling mostrerebbe più mosse in un colpo solo. La variabile d'ambiente
    ``AI_WATCH_PACE_MS`` ha la precedenza (nei test: 0 → nessuna attesa).
    """
    env = os.getenv("AI_WATCH_PACE_MS")
    if env is not None:
        return int(env)
    return int(settings_service.get(db, "ai.watch_pace_ms"))


def advance_ai(db: Session, game, session: models.GameSession) -> None:
    """Fa giocare i lati IA finché non tocca a un umano o la partita finisce.

    Commit dopo **ogni** mossa: il client in polling vede la partita avanzare (utile
    soprattutto per le sessioni IA-vs-IA, che avanzano da sole in background).
    """
    state = load_state(game, session)
    moves = json.loads(session.moves_json or "[]")
    # Ritmo di visione: OGNI mossa dell'IA rispetta un ritardo minimo dalla mossa
    # precedente (anche dalla mossa dell'umano: niente risposte-lampo "incollate"),
    # e la prima mossa della partita arriva dopo che il browser ha disegnato la
    # scacchiera. Solo in modalità asincrona: in linea bloccherebbe la richiesta
    # HTTP senza che nessuno stia guardando.
    pace_s = (_watch_pace_ms(db) / 1000.0) if async_enabled(db) else 0.0
    last_move_at = time.monotonic()  # ≈ istante della mossa che ha svegliato il worker
    # Configurazioni lette una volta per turno IA: Stockfish (base globale) e i
    # provider API. Concorrenti IA multipli: ogni lato può avere il SUO provider
    # («gioca contro Claude» vs «gioca contro Gemini»); la config viene risolta
    # per lato e memoizzata (in IA-vs-IA si alternano due lati a ogni giro).
    provider_cache: dict = {}

    def provider_for(player: int):
        code = side_provider(session, player)
        key = code or ""  # "" = provider attivo globale (comportamento storico)
        if key not in provider_cache:
            provider_cache[key] = (
                ai_providers.get_config(db, code) if code else ai_providers.get_active_config(db)
            )
        return provider_cache[key]

    stockfish_base = stockfish.get_config(db)
    think_ms = settings_service.get(db, "ai.engine_ms")
    if session.x_is_ai and session.o_is_ai:
        # IA-vs-IA: tante mosse consecutive; un budget ridotto tiene la partita fluida.
        think_ms = min(int(think_ms), 300)
    style = opponent_style(db, game, session)  # adatta il gioco al profilo dell'avversario
    while not game.is_terminal(state):
        # Giochi stocastici: prima delle mosse il server materializza il tiro dei
        # dadi (può anche far passare il turno se il tiro non è giocabile).
        if resolve_chance(db, game, session):
            state = load_state(game, session)
            moves = json.loads(session.moves_json or "[]")
            continue  # ricontrolla dal principio: turno/terminalità possono essere cambiati
        player = game.current_player(state)
        if not side_is_ai(session, player):
            break
        if pace_s > 0:
            wait = pace_s - (time.monotonic() - last_move_at)
            if wait > 0:
                time.sleep(wait)
                if session.tc_category:
                    # La pausa è "dell'arbitro", non del giocatore: l'orologio
                    # dell'IA riparte solo ora che inizia davvero a pensare.
                    session.turn_started_at = _now()
        # Orologio: se il tempo dell'IA è già scaduto la partita si chiude qui; e il
        # budget di riflessione viene limitato a una frazione del residuo, così l'IA
        # non fa cadere la propria bandierina pensando troppo a lungo.
        check_time(db, game, session)
        if session.status != "in_progress":
            return
        move_think_ms = think_ms
        sf_cfg = stockfish.config_for_level(stockfish_base, side_level(session, player))
        if session.tc_category:
            budget = max(50, _remaining_ms(session, player) // 10)
            move_think_ms = min(int(think_ms), budget)
            sf_cfg = dict(sf_cfg, move_ms=min(int(sf_cfg["move_ms"]), budget))
        move, source = opponents.choose_move(
            game,
            state,
            history_ids(moves),
            kind=side_kind(session, player),
            provider=provider_for(player),
            # Il preset del livello (Zeus/Atena/…) si applica sopra la base globale,
            # per lato: in IA-vs-IA i due lati possono avere livelli diversi.
            stockfish_cfg=sf_cfg,
            think_ms=move_think_ms,
            jitter=15,
            style=style,
        )
        # Il tempo pensato (reale) viene scalato dall'orologio dell'IA: se nel
        # frattempo la bandierina è caduta, la mossa non viene registrata.
        if not consume_time(db, game, session, player, moves):
            return
        record_move(game, state, move, player, moves)
        state = game.apply(state, move)
        # last_ai_cell è un intero (cella/colonna); per la dama la mossa è un percorso → None.
        session.last_ai_cell = move if isinstance(move, int) else None
        session.last_ai_source = source
        session.moves_json = json.dumps(moves)
        save_state(game, session, state)
        db.commit()
        # Badge di qualità + commento anche sulle mosse dell'IA (best effort).
        from . import commentary

        commentary.schedule(session.id)
        last_move_at = time.monotonic()
    finish_if_terminal(db, game, session, state)


# ----- Worker in background -----
def async_enabled(db: Session) -> bool:
    env = os.getenv("AI_ASYNC")
    if env is not None:  # override d'ambiente (nei test: 0 → sincrono)
        return env not in ("0", "false", "no", "")
    return bool(settings_service.get(db, "ai.async_moves"))


def is_running(session_id: int) -> bool:
    with _running_lock:
        return session_id in _running


def schedule_ai(db: Session, session: models.GameSession, sync_fallback: bool = True) -> None:
    """Avvia, se serve, il calcolo delle mosse IA per la sessione.

    Idempotente: al massimo un thread per sessione (richiami ripetuti e polling non ne
    creano di doppi). In modalità sincrona esegue subito in linea, ma solo se
    ``sync_fallback`` è vero (i GET di sola lettura lo passano falso).
    """
    if session.status != "in_progress":
        return
    game = get_game(session.game.code)
    state = load_state(game, session)
    if game.is_terminal(state) or not side_is_ai(session, game.current_player(state)):
        return
    if not async_enabled(db):
        if sync_fallback:
            advance_ai(db, game, session)
        return
    with _running_lock:
        if session.id in _running:
            return
        _running.add(session.id)
    threading.Thread(target=_worker, args=(session.id,), daemon=True).start()


def _worker(session_id: int) -> None:
    """Corpo del thread: sessione DB propria, mai eccezioni fuori.

    In caso d'errore la partita resta al turno dell'IA: il successivo GET dello stato
    riprogramma il calcolo (auto-ripristino, vale anche dopo un riavvio del server).
    """
    db = SessionLocal()
    try:
        session = db.get(models.GameSession, session_id)
        if session and session.status == "in_progress":
            advance_ai(db, get_game(session.game.code), session)
    except Exception:  # noqa: BLE001 - il worker non deve abbattere il processo
        logger.exception("Errore del worker IA sulla sessione %s", session_id)
    finally:
        db.close()
        with _running_lock:
            _running.discard(session_id)
