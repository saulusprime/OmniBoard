"""Sessioni di gioco giocabili (umano vs umano, umano vs IA, IA vs IA).

Il backend mantiene lo stato della partita e il log delle mosse e valida le mosse
tramite il motore. Le mosse dei lati IA vengono calcolate **in background** (vedi
``gameplay``): gli endpoint rispondono subito e il client si aggiorna via polling
di ``GET /sessions/{id}``. A fine partita i punteggi dei giocatori umani vengono
aggiornati; il log resta consultabile nello storico dei giocatori.
"""

from __future__ import annotations

import json
import random
import textwrap

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine import get_game, is_playable
from engine.chess import pgn as chess_pgn

from .. import (
    ai_providers,
    analysis,
    commentary,
    gameplay,
    gifexport,
    models,
    opponents,
    ponder,
    schemas,
    settings_service,
    tilt,
    user_prefs,
)
from ..database import get_db
from ..i18n import _
from ..opponents import api_ai
from .auth import session_from_token

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _view(session: models.GameSession) -> dict:
    game = get_game(session.game.code)
    state = gameplay.load_state(game, session)
    finished = session.status == "finished"

    current = None
    current_is_ai = False
    legal: list[int] = []
    playable_moves: list[dict] = []
    if not finished:
        player = game.current_player(state)
        current = "x" if player == 0 else "o"
        current_is_ai = gameplay.side_is_ai(session, player)
        # Per i giochi a indice (Tris/Forza 4) il client usa gli interi; per la dama
        # usa la lista strutturata `playable_moves` (origine/destinazione/catture).
        legal = [m for m in game.legal_moves(state) if isinstance(m, int)]
        playable_moves = game.legal_moves_view(state)

    moves = json.loads(session.moves_json or "[]")
    # Preferenze estetiche dei giocatori umani (tema scacchiera, segno del Tris);
    # per i lati IA valgono i default. Se i due umani hanno scelto lo STESSO segno,
    # il lato O ripiega sul default per mantenere i segni distinguibili.
    x_prefs = user_prefs.get_prefs(session.x_user)
    o_prefs = user_prefs.get_prefs(session.o_user)
    x_mark = (x_prefs.get("tris_mark") or "X") if session.x_user else "X"
    o_mark = (o_prefs.get("tris_mark") or "O") if session.o_user else "O"
    if o_mark == x_mark:
        o_mark = "O" if x_mark != "O" else "X"
    return {
        "id": session.id,
        "game_code": session.game.code,
        # Partita a distanza: il client abilita solo il PROPRIO lato e fa polling
        # mentre aspetta la mossa dell'avversario (umano remoto o IA).
        "remote": bool(session.remote),
        "game_name": game.name,
        "rows": game.rows,
        "cols": game.cols,
        "move_type": game.move_type,
        "status": session.status,
        "board": game.view_board(state),
        "current": current,
        "current_is_ai": current_is_ai,
        "ai_thinking": current_is_ai and gameplay.is_running(session.id),
        "legal_moves": legal,
        "playable_moves": playable_moves,
        "winner": session.winner,
        "finish_reason": session.finish_reason,  # time | repetition | resign | agreement
        # Posizione iniziale personalizzata (FEN, solo scacchi); None = standard.
        "start_fen": session.start_fen,
        # Patta d'accordo: lato con offerta PENDENTE ("x"/"o", None = nessuna).
        "draw_offer": session.draw_offer,
        "clock": gameplay.clock_view(session, game),  # None se partita senza orologio
        # Riga informativa specifica del gioco (es. "Dadi da giocare: 5 3" nel
        # backgammon); None per i giochi che non ne hanno bisogno.
        "status_line": game.view_status(state),
        "opening": _(game.opening_name(gameplay.history_ids(moves)) or "") or None,
        "moves": moves,
        "players": {
            # type ∈ {"human", "ai" (IA via API), "stockfish"} — vedi gameplay.side_kind.
            # level/level_label: preset Stockfish (es. "zeus" / «Zeus (Extreme)»).
            "x": {
                "type": gameplay.side_kind(session, 0),
                "user_id": session.x_user_id,
                "alias": session.x_user.alias if session.x_user else None,
                "level": session.x_ai_level,
                # Etichetta del livello: preset Stockfish o livello del motore locale.
                "level_label": opponents.stockfish.preset_label(session.x_ai_level)
                or opponents.local.level_label(session.x_ai_level),
                # Concorrente IA del lato («gioca contro …»); None = provider attivo.
                "provider": session.x_ai_provider,
                "provider_label": ai_providers.provider_label(session.x_ai_provider),
                # Estetica scelta dal giocatore: tema scacchiera e segno del Tris.
                "board_theme": x_prefs.get("board_theme") if session.x_user else None,
                "mark": x_mark,
            },
            "o": {
                "type": gameplay.side_kind(session, 1),
                "user_id": session.o_user_id,
                "alias": session.o_user.alias if session.o_user else None,
                "level": session.o_ai_level,
                "level_label": opponents.stockfish.preset_label(session.o_ai_level)
                or opponents.local.level_label(session.o_ai_level),
                "provider": session.o_ai_provider,
                "provider_label": ai_providers.provider_label(session.o_ai_provider),
                "board_theme": o_prefs.get("board_theme") if session.o_user else None,
                "mark": o_mark,
            },
        },
        # Ultima mossa IA: "source" dice chi ha giocato davvero (book / stockfish /
        # <provider> / engine / local); "cell" è valorizzata solo per i giochi a
        # indice (Tris/Forza 4), per scacchi/dama la mossa è un percorso.
        "last_ai": (
            {"cell": session.last_ai_cell, "source": session.last_ai_source}
            if session.last_ai_source is not None
            else None
        ),
    }


@router.post("", status_code=201)
def create_session(payload: schemas.SessionCreate, db: Session = Depends(get_db)):
    game_model = db.query(models.Game).filter_by(code=payload.game_code).first()
    if not game_model:
        raise HTTPException(status_code=404, detail=_("Gioco non trovato"))
    if not is_playable(payload.game_code):
        raise HTTPException(status_code=400, detail=_("Gioco non ancora giocabile"))
    game = get_game(payload.game_code)

    def resolve(spec: schemas.PlayerSpec):
        """(user_id, is_ai, ai_kind, level, provider) per un lato.

        Umano, IA via API (con eventuale CONCORRENTE scelto: Claude/Gemini/Grok/…)
        o Stockfish (con eventuale preset di livello).
        """
        if spec.type == "stockfish":
            # Il livello è un preset noto ("zeus", "atena", …) o None (parametri globali).
            if spec.level and spec.level not in opponents.stockfish.PRESETS:
                raise HTTPException(status_code=400, detail=_("Livello Stockfish sconosciuto"))
            return None, True, spec.type, spec.level, None
        if spec.type == "ai":
            # provider None = provider attivo globale (comportamento storico).
            if spec.provider and not ai_providers.is_known(spec.provider):
                raise HTTPException(status_code=400, detail=_("Provider IA sconosciuto"))
            # Livello del MOTORE LOCALE: alternativo al provider (lo scavalca).
            if spec.level:
                if spec.level not in opponents.local.ENGINE_LEVELS:
                    raise HTTPException(status_code=400, detail=_("Livello del motore sconosciuto"))
                if spec.provider:
                    raise HTTPException(
                        status_code=400,
                        detail=_(
                            "Livello e provider insieme non hanno senso: "
                            "il livello calibra il motore locale"
                        ),
                    )
            return None, True, spec.type, spec.level, spec.provider
        if not spec.user_id:
            raise HTTPException(status_code=400, detail=_("Manca l'utente per un giocatore umano"))
        if not db.get(models.User, spec.user_id):
            raise HTTPException(status_code=404, detail=_("Utente non trovato"))
        return spec.user_id, False, None, None, None

    x_uid, x_ai, x_kind, x_level, x_provider = resolve(payload.x)
    o_uid, o_ai, o_kind, o_level, o_provider = resolve(payload.o)

    # Anti-tilt FORZATO (solo opzione admin; il default è l'avviso soft nel
    # setup): a blocco attivo un giocatore in tilt non apre nuove partite di
    # scacchi finché non è passato il raffreddamento. Mai sulle partite in corso.
    if payload.game_code == "chess":
        for uid in {u for u in (x_uid, o_uid) if u}:
            reason = tilt.block_new_game(db, uid)
            if reason:
                raise HTTPException(status_code=403, detail=reason)

    # Orologio di gioco (solo scacchi): valida categoria/minuti/incremento Fischer.
    try:
        time_control = gameplay.build_time_control(
            payload.game_code, payload.time_category, payload.time_base_min, payload.time_inc_s
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Posizione iniziale personalizzata (FEN, solo scacchi): validata col motore
    # e NORMALIZZATA (to_fen) prima di essere salvata — replay, analisi, Stockfish
    # e ripetizioni ripartiranno tutti da qui. Negli scacchi X resta il Bianco:
    # se la FEN dà il tratto al Nero, la prima mossa spetta al lato O.
    start_fen = None
    if payload.start_fen and payload.start_fen.strip():
        if payload.game_code != "chess":
            raise HTTPException(
                status_code=400, detail=_("La posizione iniziale FEN vale solo per gli scacchi")
            )
        try:
            state = game.from_fen(payload.start_fen.strip())
            if state.board.count("K") != 1 or state.board.count("k") != 1:
                raise ValueError("servono esattamente i due re")
            if game._in_check(state, 1 - state.current):
                raise ValueError("il giocatore senza il tratto è sotto scacco")
            if game.is_terminal(state):
                raise ValueError("la posizione è già conclusa")
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=_("FEN non valida: {err}").format(err=exc)
            ) from exc
        except Exception as exc:  # noqa: BLE001 - FEN malformata: indici/valori fuori posto
            raise HTTPException(status_code=400, detail=_("FEN non valida")) from exc
        start_fen = game.to_fen(state)
    else:
        state = game.initial_state()
    session = models.GameSession(
        game_id=game_model.id,
        x_user_id=x_uid,
        o_user_id=o_uid,
        x_is_ai=x_ai,
        o_is_ai=o_ai,
        x_ai_kind=x_kind,
        o_ai_kind=o_kind,
        x_ai_level=x_level,
        o_ai_level=o_level,
        x_ai_provider=x_provider,
        o_ai_provider=o_provider,
        remote=payload.remote,
        start_fen=start_fen,
        state_json=json.dumps(game.serialize_state(state)),
        moves_json="[]",
        status="in_progress",
    )
    gameplay.init_clock(session, time_control)  # l'orologio di X parte da subito
    db.add(session)
    db.commit()
    db.refresh(session)

    gameplay.resolve_chance(db, session=session, game=game)  # es. primo tiro di dadi
    gameplay.schedule_ai(db, session)  # se il primo a muovere è l'IA, pensa in background
    return _view(session)


@router.post("/batch", status_code=201)
def run_batch(payload: schemas.BatchCreate, db: Session = Depends(get_db)):
    """Gioca ``count`` partite consecutive IA-vs-IA e restituisce il riepilogo.

    Non persiste le singole partite (nessun giocatore umano, nessun punteggio): è una
    simulazione sincrona con budget motore ridotto.
    """
    if not db.query(models.Game).filter_by(code=payload.game_code).first():
        raise HTTPException(status_code=404, detail=_("Gioco non trovato"))
    if not is_playable(payload.game_code):
        raise HTTPException(status_code=400, detail=_("Gioco non ancora giocabile"))
    max_batch = int(settings_service.get(db, "games.batch_max"))
    if payload.count > max_batch:
        raise HTTPException(
            status_code=400,
            detail=_("Numero massimo di partite consecutive: {n}").format(n=max_batch),
        )
    game = get_game(payload.game_code)

    provider = ai_providers.get_active_config(db)
    # Nel batch il motore scacchi usa un tempo ridotto (tante partite × tante mosse) e un
    # po' di jitter per non ripetere identica la stessa partita (motore deterministico).
    # Entrambi i lati sono IA di tipo "ai" (API con ripiego sul giocatore locale).
    batch_ms = min(120, int(settings_service.get(db, "ai.engine_ms")))
    tally = {"x": 0, "o": 0, "draw": 0}
    for _game_n in range(payload.count):  # NB: '_' è la funzione di traduzione
        state = game.initial_state()
        history: list[str] = []
        while not game.is_terminal(state):
            if game.is_chance_node(state):
                # Giochi stocastici (backgammon): nel batch il tiro dei dadi viene
                # estratto qui, senza log (la simulazione non viene persistita).
                outcomes = game.chance_outcomes(state)
                event = random.choices(
                    [e for e, _p in outcomes], weights=[p for _e, p in outcomes], k=1
                )[0]
                state = game.apply_chance(state, event)
                continue
            move, _source = opponents.choose_move(
                game, state, history, kind="ai", provider=provider, think_ms=batch_ms, jitter=20
            )
            history.append(game.move_id(move))
            state = game.apply(state, move)
        winner = game.outcome(state).winner
        key = "draw" if winner is None else ("x" if winner == 0 else "o")
        tally[key] += 1

    return {
        "game_code": payload.game_code,
        "count": payload.count,
        "x_wins": tally["x"],
        "o_wins": tally["o"],
        "draws": tally["draw"],
    }


@router.get("/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):
    session = db.get(models.GameSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=_("Sessione non trovata"))
    game = get_game(session.game.code)
    # Nodi del caso pigri: chi legge lo stato materializza l'eventuale tiro di dadi.
    gameplay.resolve_chance(db, game, session)
    # Bandierina pigra: l'orologio è autorevole anche se nessuno muove più — la
    # lettura di stato (il polling del client) chiude la partita a tempo scaduto.
    gameplay.check_time(db, game, session)
    # Auto-ripristino: se è il turno dell'IA e nessun worker è attivo (es. server
    # riavviato a metà pensata), il polling stesso riprogramma il calcolo.
    gameplay.schedule_ai(db, session, sync_fallback=False)
    return _view(session)


@router.post("/{session_id}/move")
def make_move(
    session_id: int,
    payload: schemas.MoveIn,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    session = db.get(models.GameSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=_("Sessione non trovata"))
    ponder.stop(session_id)  # l'umano ha mosso: si smette di ponderare (TT conservata)

    game = get_game(session.game.code)
    # Nodi del caso: se i dadi sono ancora da tirare, si tirano ora (server-side).
    gameplay.resolve_chance(db, game, session)
    # L'orologio decide prima della mossa: se il tempo del giocatore è già scaduto,
    # la partita viene chiusa e la mossa rifiutata.
    gameplay.check_time(db, game, session)
    if session.status == "finished":
        raise HTTPException(status_code=409, detail=_("Partita già conclusa"))

    state = gameplay.load_state(game, session)
    player = game.current_player(state)
    if gameplay.side_is_ai(session, player):
        raise HTTPException(status_code=409, detail=_("È il turno dell'IA"))
    if session.remote:
        # Partita a distanza: SOLO il giocatore al tratto può muovere, autenticato
        # col proprio token di sessione (i client sono indipendenti e non fidati).
        # L'hotseat (remote=False) resta com'era: nessun token richiesto.
        mover = session_from_token(db, x_auth_token).user  # 401 se manca/scaduto
        owner_id = session.x_user_id if player == 0 else session.o_user_id
        if mover.id != owner_id:
            raise HTTPException(
                status_code=403, detail=_("Non sei il giocatore al tratto in questa partita")
            )
    chosen = next((m for m in game.legal_moves(state) if game.move_id(m) == payload.move), None)
    if chosen is None:
        raise HTTPException(status_code=400, detail=_("Mossa non valida"))

    moves = json.loads(session.moves_json or "[]")
    # Scala il tempo pensato dall'orologio del giocatore (con incremento a mossa
    # completata); se la bandierina è caduta nel frattempo, la mossa arriva tardi.
    if not gameplay.consume_time(db, game, session, player, moves):
        raise HTTPException(status_code=409, detail=_("Tempo scaduto: partita conclusa"))
    if session.draw_offer and session.draw_offer != ("x" if player == 0 else "o"):
        session.draw_offer = None  # muovere = rifiutare l'offerta pendente (FIDE 9.1)
    gameplay.record_move(game, state, chosen, player, moves)
    state = game.apply(state, chosen)
    session.moves_json = json.dumps(moves)
    gameplay.save_state(game, session, state)
    session.last_ai_cell = None
    session.last_ai_source = None
    db.commit()

    gameplay.finish_if_terminal(db, game, session, state)
    # Badge di qualità + commento LLM sull'ultima mossa (best effort, in background).
    commentary.schedule(session.id)
    if session.status != "finished":
        # Se il turno è passato a un nodo del caso (backgammon: dadi del prossimo
        # giocatore), la risposta include già il tiro: chi gioca in locale in due
        # non deve aspettare un polling per vedere i propri dadi.
        gameplay.resolve_chance(db, game, session)
        gameplay.schedule_ai(db, session)  # la risposta parte subito, l'IA pensa in background
    return _view(session)


# ----- Moviola, note, analisi post-partita ed export GIF -----
def _replay_boards(session: models.GameSession):
    """Le posizioni della partita, dalla iniziale a quella dopo l'ultima semimossa.

    Ricostruite col motore (apply su ogni id del log): sono la base della moviola
    (rewind/step-by-step) e dei fotogrammi della GIF.
    """
    game = get_game(session.game.code)
    state = game.from_fen(session.start_fen) if session.start_fen else game.initial_state()
    boards = [game.view_board(state)]
    moves = json.loads(session.moves_json or "[]")
    for uci in gameplay.history_ids(moves):
        move = next((m for m in game.legal_moves(state) if game.move_id(m) == uci), None)
        if move is None:  # log corrotto o gioco stocastico non ricostruibile: stop
            break
        state = game.apply(state, move)
        boards.append(game.view_board(state))
    return game, boards


@router.get("/{session_id}/replay")
def replay(session_id: int, db: Session = Depends(get_db)):
    """Moviola: tutte le posizioni della partita (indice 0 = posizione iniziale)."""
    session = db.get(models.GameSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=_("Sessione non trovata"))
    game, boards = _replay_boards(session)
    return {"rows": game.rows, "cols": game.cols, "boards": boards}


@router.get("/{session_id}/pgn")
def export_pgn(session_id: int, db: Session = Depends(get_db)):
    """Export PGN della partita (solo scacchi): tag standard + mosse in SAN.

    Le note dei giocatori diventano commenti PGN ``{…}``; le partite da FEN
    hanno i tag ``SetUp``/``FEN``. Risposta come allegato ``partita-N.pgn``.
    """
    session = db.get(models.GameSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=_("Sessione non trovata"))
    if session.game.code != "chess":
        raise HTTPException(status_code=400, detail=_("L'export PGN vale solo per gli scacchi"))
    game = get_game("chess")
    moves = json.loads(session.moves_json or "[]")
    sans = chess_pgn.san_line(game, gameplay.history_ids(moves), start_fen=session.start_fen)

    def side_name(idx: int) -> str:
        user = session.x_user if idx == 0 else session.o_user
        if user:
            return user.alias
        kind = gameplay.side_kind(session, idx)
        level = session.x_ai_level if idx == 0 else session.o_ai_level
        if kind == "stockfish":
            label = opponents.stockfish.preset_label(level)
            return f"Stockfish — {label}" if label else "Stockfish"
        provider = session.x_ai_provider if idx == 0 else session.o_ai_provider
        label = ai_providers.provider_label(provider) or opponents.local.level_label(level)
        return f"IA — {label}" if label else "IA"

    result = {"x": "1-0", "o": "0-1", "draw": "1/2-1/2"}.get(session.winner or "", "*")
    tags = [
        ("Event", str(settings_service.get(db, "general.site_name") or "Scacchi")),
        ("Site", f"partita {session.id}"),
        ("Date", session.created_at.strftime("%Y.%m.%d") if session.created_at else "????.??.??"),
        ("Round", "-"),
        ("White", side_name(0)),
        ("Black", side_name(1)),
        ("Result", result),
    ]
    if session.start_fen:
        tags += [("SetUp", "1"), ("FEN", session.start_fen)]

    # Movetext: numerazione dalla 1 (con "1..." se da FEN muove il Nero); le note
    # dei giocatori seguono la mossa come commenti.
    black_first = bool(session.start_fen) and session.start_fen.split()[1] == "b"
    tokens: list[str] = []
    for i, san in enumerate(sans):
        number = (i + 1) // 2 + 1 if black_first else i // 2 + 1
        if black_first:
            if i == 0:
                tokens.append("1...")
            elif i % 2 == 1:
                tokens.append(f"{number}.")
        elif i % 2 == 0:
            tokens.append(f"{number}.")
        tokens.append(san)
        note = (moves[i].get("note") or "").replace("{", "(").replace("}", ")")
        if note:
            tokens.append("{" + note + "}")
    tokens.append(result)

    lines = [f'[{key} "{value}"]' for key, value in tags]
    lines.append("")
    lines.extend(textwrap.wrap(" ".join(tokens), width=80) or [result])
    return PlainTextResponse(
        "\n".join(lines) + "\n",
        media_type="application/x-chess-pgn",
        headers={"Content-Disposition": f'attachment; filename="partita-{session.id}.pgn"'},
    )


class ExplainIn(BaseModel):
    ply: int  # 1-based: la semimossa da spiegare


@router.post("/{session_id}/explain")
def explain_move(session_id: int, payload: ExplainIn, db: Session = Depends(get_db)):
    """«Spiegami questa mossa»: l'LLM spiega in parole semplici una semimossa.

    Il modello SPIEGA e non gioca: il prompt gli porta solo dati GIÀ prodotti
    (posizione, valutazione e mossa preferita dall'analisi, badge di qualità,
    apertura, eventuale nota del giocatore). La spiegazione viene salvata nello
    storico della mossa (``explain``): il secondo clic non richiama il modello e
    il testo ricompare in moviola. Protetta dal circuit breaker del provider.
    """
    session = db.get(models.GameSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=_("Sessione non trovata"))
    if session.game.code != "chess":
        raise HTTPException(status_code=400, detail=_("Disponibile solo per gli scacchi"))
    if not settings_service.get(db, "coach.explain_enabled"):
        raise HTTPException(status_code=403, detail=_("Funzione disattivata dal super admin"))
    moves = json.loads(session.moves_json or "[]")
    if not (1 <= payload.ply <= len(moves)):
        raise HTTPException(status_code=400, detail=_("Semimossa inesistente"))
    rec = moves[payload.ply - 1]
    if rec.get("explain"):
        return {"ply": payload.ply, "text": rec["explain"], "cached": True}

    provider = ai_providers.get_active_config(db)
    if provider is None:
        raise HTTPException(
            status_code=503, detail=_("Nessun provider IA attivo (configura un token)")
        )

    game = get_game("chess")
    history = gameplay.history_ids(moves)
    # Posizione PRIMA della mossa, rigiocata col motore (anche da FEN).
    state = game.from_fen(session.start_fen) if session.start_fen else game.initial_state()
    for uci in history[: payload.ply - 1]:
        move = next((m for m in game.legal_moves(state) if game.move_id(m) == uci), None)
        if move is None:
            raise HTTPException(status_code=409, detail=_("Storico non ricostruibile"))
        state = game.apply(state, move)
    mover = "il Bianco" if state.current == 0 else "il Nero"

    # Dati GIÀ prodotti: analisi (valutazione/perdita/mossa migliore), badge, apertura.
    fatti = [f"posizione prima della mossa (FEN): {game.to_fen(state)}"]
    ev = None
    if session.analysis_json:
        evals = (json.loads(session.analysis_json) or {}).get("evals") or []
        ev = next((e for e in evals if e.get("ply") == payload.ply), None)
    if ev:
        fatti.append(
            f"dopo la mossa il motore valuta {ev['cp'] / 100:+.1f} pedoni "
            "(punto di vista del Bianco)"
        )
        if ev.get("loss"):
            fatti.append(f"chi ha mosso ha perso ~{ev['loss'] / 100:.1f} pedoni rispetto al meglio")
        if ev.get("best"):
            fatti.append(f"il motore preferiva {ev['best']}")
    quality = rec.get("quality")
    if quality:
        fatti.append(f"giudizio sintetico: {quality.get('label', '')}")
    opening = game.opening_name(history[: payload.ply])
    if opening:
        fatti.append(f"apertura: {opening}")
    if rec.get("note"):
        fatti.append(f"nota del giocatore: «{rec['note']}»")

    prompt = (
        "Sei un istruttore di scacchi paziente, in italiano. Spiega in parole semplici "
        f"la semimossa {payload.ply} della partita: {mover} ha giocato "
        f"{rec.get('notation') or rec.get('id')}. Dati del motore: "
        + "; ".join(fatti)
        + ". Spiega COSA fa la mossa e PERCHÉ è buona o cattiva (e, se c'era di meglio, "
        "cosa e perché) in AL MASSIMO 3 frasi, senza sommergere di varianti. "
        "Tu spieghi soltanto: non proporre di continuare la partita."
    )
    text = api_ai.guarded_complete(provider, prompt)
    if not text:
        raise HTTPException(
            status_code=503,
            detail=_("Provider IA non disponibile al momento (errore o circuito aperto): riprova"),
        )
    text = " ".join(text.split())[:600]
    rec["explain"] = text
    session.moves_json = json.dumps(moves)
    db.commit()
    return {"ply": payload.ply, "text": text, "cached": False}


class NoteIn(BaseModel):
    ply: int  # 1-based: la semimossa a cui la nota si riferisce
    text: str  # vuoto = cancella la nota


@router.post("/{session_id}/note")
def save_note(
    session_id: int,
    payload: NoteIn,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Salva una nota su una semimossa, DENTRO lo storico della partita.

    La nota vive nel log delle mosse (``moves_json``): compare nella moviola e
    nello storico del giocatore. Nelle partite a distanza può scrivere solo chi
    vi ha giocato (token); in hotseat resta aperto, come le mosse.
    """
    session = db.get(models.GameSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=_("Sessione non trovata"))
    if session.remote:
        writer = session_from_token(db, x_auth_token).user
        if writer.id not in (session.x_user_id, session.o_user_id):
            raise HTTPException(status_code=403, detail=_("Solo i giocatori possono annotare"))
    moves = json.loads(session.moves_json or "[]")
    if not (1 <= payload.ply <= len(moves)):
        raise HTTPException(status_code=400, detail=_("Semimossa inesistente"))
    text = payload.text.strip()[:500]
    if text:
        moves[payload.ply - 1]["note"] = text
    else:
        moves[payload.ply - 1].pop("note", None)  # nota vuota = cancellazione
    session.moves_json = json.dumps(moves)
    db.commit()
    return {"ply": payload.ply, "note": text or None}


@router.post("/{session_id}/analysis", status_code=202)
def start_analysis(session_id: int, db: Session = Depends(get_db)):
    """Avvia l'analisi post-partita (solo scacchi, partita conclusa)."""
    session = db.get(models.GameSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=_("Sessione non trovata"))
    if session.game.code != "chess":
        raise HTTPException(
            status_code=400, detail=_("L'analisi è disponibile solo per gli scacchi")
        )
    if session.status != "finished":
        raise HTTPException(status_code=409, detail=_("La partita non è ancora conclusa"))
    if not opponents.stockfish.is_available(opponents.stockfish.get_config(db)):
        raise HTTPException(status_code=503, detail=_("Stockfish non disponibile per l'analisi"))
    if session.analysis_json:  # già calcolata: si rilegge, niente doppio lavoro
        return {"started": False, "already_done": True}
    return {"started": analysis.start(session_id), "already_done": False}


@router.get("/{session_id}/analysis")
def get_analysis(session_id: int, db: Session = Depends(get_db)):
    """Stato/risultato dell'analisi (il client fa polling finché ``running``)."""
    session = db.get(models.GameSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=_("Sessione non trovata"))
    if analysis.is_running(session_id):
        return {"status": "running"}
    if not session.analysis_json:
        return {"status": "none"}
    return json.loads(session.analysis_json)


@router.get("/{session_id}/gif")
def export_gif(session_id: int, db: Session = Depends(get_db)):
    """L'intera partita come GIF animata (un fotogramma per posizione)."""
    session = db.get(models.GameSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=_("Sessione non trovata"))
    game, boards = _replay_boards(session)
    if not gifexport.supported(game.move_type):
        raise HTTPException(status_code=400, detail=_("Export GIF non supportato per questo gioco"))
    data = gifexport.render(boards, game.rows, game.cols, game.move_type)
    return Response(
        content=data,
        media_type="image/gif",
        headers={"Content-Disposition": f'attachment; filename="partita-{session_id}.gif"'},
    )


@router.post("/{session_id}/hint")
def move_hint(
    session_id: int,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Suggerimento di mossa per il giocatore umano al tratto (motore a budget ridotto).

    Riservato ai PRINCIPIANTI: negato a chi supera ``hints.max_wins`` vittorie nel
    gioco in corso (per gli scacchi = partite di scacchi vinte). Negato anche nel
    formato FIDE ufficiale — e lo sarà nei tornei/campionati quando esisteranno.
    Nelle partite a distanza serve il token del giocatore al tratto.
    """
    session = db.get(models.GameSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=_("Sessione non trovata"))
    if not settings_service.get(db, "hints.enabled"):
        raise HTTPException(status_code=403, detail=_("Suggerimenti disattivati dal super admin"))
    if session.tc_category == "fide":
        raise HTTPException(
            status_code=403, detail=_("Formato ufficiale FIDE: suggerimenti non ammessi")
        )
    if session.status != "in_progress":
        raise HTTPException(status_code=409, detail=_("La partita non è in corso"))

    game = get_game(session.game.code)
    gameplay.resolve_chance(db, game, session)
    state = gameplay.load_state(game, session)
    player = game.current_player(state)
    if gameplay.side_is_ai(session, player):
        raise HTTPException(status_code=409, detail=_("È il turno dell'IA"))
    user_id = session.x_user_id if player == 0 else session.o_user_id
    if session.remote:
        mover = session_from_token(db, x_auth_token).user
        if mover.id != user_id:
            raise HTTPException(
                status_code=403, detail=_("Il suggerimento è del giocatore al tratto")
            )
    # Riservato ai principianti: chi ha già troppe vittorie in QUESTO gioco non lo usa
    # (e in una partita fra esperti nessuno dei due può chiederlo).
    if user_id:
        score = db.query(models.Score).filter_by(user_id=user_id, game_id=session.game_id).first()
        max_wins = int(settings_service.get(db, "hints.max_wins"))
        if score and score.wins > max_wins:
            raise HTTPException(
                status_code=403,
                detail=_("Suggerimenti riservati ai principianti (max {n} vittorie)").format(
                    n=max_wins
                ),
            )

    legal = list(game.legal_moves(state))
    moves_log = json.loads(session.moves_json or "[]")
    move, _source = opponents.local.best_move(
        game,
        state,
        legal,
        history=gameplay.history_ids(moves_log),
        think_ms=int(settings_service.get(db, "hints.engine_ms")),
    )
    return {"move": game.move_id(move), "notation": game.describe_move(state, move)}


# ----- Abbandono (FIDE 5.1.2) e patta d'accordo (FIDE 9.1) -----
class SideAction(BaseModel):
    side: str  # "x" oppure "o": chi compie l'azione


class DrawAction(BaseModel):
    side: str
    action: str = "offer"  # offer | accept | decline


def _acting_human(session, payload_side: str, db, token: str):
    """Valida chi agisce: lato esistente, UMANO, e nei remote il token corrisponde.

    Stesse regole di fiducia delle mosse: in hotseat ci si fida dello schermo,
    a distanza l'identità è verificata dal token di sessione.
    """
    side = (payload_side or "").lower()
    if side not in ("x", "o"):
        raise HTTPException(status_code=400, detail=_("Lato non valido (x oppure o)"))
    is_ai = session.x_is_ai if side == "x" else session.o_is_ai
    if is_ai:
        raise HTTPException(status_code=400, detail=_("Solo un giocatore umano può farlo"))
    if session.remote:
        actor = session_from_token(db, token).user
        owner = session.x_user_id if side == "x" else session.o_user_id
        if actor.id != owner:
            raise HTTPException(status_code=403, detail=_("Puoi agire solo per il tuo lato"))
    return side


@router.post("/{session_id}/resign")
def resign(
    session_id: int,
    payload: SideAction,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Abbandono: l'avversario vince (FIDE 5.1.2).

    Sfumatura del regolamento: se all'avversario resta il RE NUDO (non può dare
    matto), l'abbandono produce PATTA — stessa semplificazione della bandierina.
    """
    session = db.get(models.GameSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=_("Sessione non trovata"))
    if session.status != "in_progress":
        raise HTTPException(status_code=409, detail=_("La partita non è in corso"))
    side = _acting_human(session, payload.side, db, x_auth_token)

    game = get_game(session.game.code)
    state = gameplay.load_state(game, session)
    winner = "o" if side == "x" else "x"
    if game.code == "chess":
        resigner = 0 if side == "x" else 1
        winner = gameplay._winner_on_time(game, state, resigner)  # riusa la regola 6.9
    gameplay.finish_manual(db, session, winner, "resign")
    return _view(session)


@router.post("/{session_id}/draw")
def draw_agreement(
    session_id: int,
    payload: DrawAction,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    """Patta d'accordo (FIDE 9.1): offri / accetta / rifiuta.

    Un'offerta resta pendente finché l'avversario non risponde — anche muovendo
    (la mossa vale come rifiuto). Contro l'IA l'accordo non è disponibile.
    """
    session = db.get(models.GameSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=_("Sessione non trovata"))
    if session.status != "in_progress":
        raise HTTPException(status_code=409, detail=_("La partita non è in corso"))
    side = _acting_human(session, payload.side, db, x_auth_token)
    other_is_ai = session.o_is_ai if side == "x" else session.x_is_ai

    if payload.action == "offer":
        if other_is_ai:
            raise HTTPException(
                status_code=409, detail=_("Contro l'IA la patta d'accordo non è disponibile")
            )
        if session.draw_offer == side:
            raise HTTPException(status_code=409, detail=_("Hai già un'offerta pendente"))
        if session.draw_offer:  # l'avversario aveva già offerto: offrire = accettare
            gameplay.finish_manual(db, session, "draw", "agreement")
            return _view(session)
        session.draw_offer = side
        db.commit()
    elif payload.action == "accept":
        if not session.draw_offer or session.draw_offer == side:
            raise HTTPException(status_code=409, detail=_("Nessuna offerta da accettare"))
        gameplay.finish_manual(db, session, "draw", "agreement")
    elif payload.action == "decline":
        if not session.draw_offer or session.draw_offer == side:
            raise HTTPException(status_code=409, detail=_("Nessuna offerta da rifiutare"))
        session.draw_offer = None
        db.commit()
    else:
        raise HTTPException(status_code=400, detail=_("Azione non valida (offer/accept/decline)"))
    return _view(session)
