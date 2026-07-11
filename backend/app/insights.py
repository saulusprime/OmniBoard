"""Statistiche avanzate del giocatore e raccolta delle «mosse geniali».

Aggrega SOLO materia prima già in casa (mai RICERCA del motore qui; l'unico
lavoro scacchistico è il replay deterministico delle mosse per riconoscere le
fasi della partita):

- punteggi e rating per gioco (``scores``/``ratings``);
- profilo scacchistico in cache (accuracy, colori, aperture — ``profile_cache``);
- **serie** (vittorie consecutive, migliore e corrente) per gioco;
- distribuzione degli **esiti** delle partite di scacchi (matto/tempo/abbandono/
  patta d'accordo/ripetizione);
- la valutazione per i **quattro aspetti** del gioco (aperture, tattica,
  strategia, finali) dalle analisi già calcolate — v. ``_aspects``;
- conteggio dei **badge di qualità** sulle PROPRIE mosse (🌟👍⚔️🐔🤔😬🤡,
  assegnati dal commentatore in ``moves_json``);
- la raccolta delle **mosse geniali**: le proprie mosse coi badge 💎 («geniale,
  sacrificio» — mossa forte che OFFRE materiale, misurato con la SEE del motore)
  e 🌟 («da maestro»), con avversario, data, pezzo (per i filtri della galleria)
  e aggancio alla moviola sulla semimossa esatta. Lo «screenshot» è
  ``GET /sessions/{id}/board.png?ply=N`` (renderer Pillow della GIF).
"""

from __future__ import annotations

import json

from sqlalchemy import or_
from sqlalchemy.orm import Session

from engine import get_game
from engine.chess import openings

from . import ai_arena, models, profile_cache, rating
from .i18n import _

CHESS_CODE = "chess"
BADGE_SYMBOLS = ("💎", "🌟", "👍", "⚔️", "🐔", "🤔", "😬", "🤡")
BRILLIANT = ("💎", "🌟")  # geniali (sacrificio) e da maestro

# Fasce dei QUATTRO ASPETTI: apertura = prime ~12 mosse; finale = al più 6
# pezzi non-pedone sulla scacchiera (re esclusi); in mezzo, il mediogioco.
_OPENING_PLIES = 24
_ENDGAME_PIECES = 6
_NONPAWN_PIECES = set("♕♖♗♘♛♜♝♞")  # come appaiono in view_board
_ASPECT_GAMES = 40  # tetto di partite rigiocate (il replay costa, l'analisi no)
_ASPECT_MIN_MOVES = 10  # sotto questo campione il punteggio non fa testo
_ASPECT_MIN_GAMES = 3  # campione minimo di partite per giudicare la tattica
_PUNISH_LOSS = 100  # risposta a un blunder che "tiene" il vantaggio (cp persi)

# Sottocategorie tattiche: soglie in centipedoni. Una mossa "concede" una
# tattica da _TACTIC_LOSS in su (almeno un pezzo leggero); i matti nell'analisi
# sono codificati ±(10000 − distanza), quindi |cp| ≥ 9901 = matto forzato.
_TACTIC_LOSS = 250
_MATE_CP = 9901
_HANG_ROOK = 450  # perdita da torre in su (fino alla donna)
_HANG_QUEEN = 850  # perdita da donna in su


def _user_sessions(db: Session, user_id: int, game_code: str | None = None):
    q = (
        db.query(models.GameSession)
        .join(models.Game)
        .filter(
            models.GameSession.status == "finished",
            or_(
                models.GameSession.x_user_id == user_id,
                models.GameSession.o_user_id == user_id,
            ),
        )
    )
    if game_code:
        q = q.filter(models.Game.code == game_code)
    return q.order_by(models.GameSession.id.asc()).all()


def _result_for(session: models.GameSession, user_id: int) -> str:
    side = "x" if session.x_user_id == user_id else "o"
    if session.winner == "draw" or session.winner is None:
        return "draw"
    return "win" if session.winner == side else "loss"


def _opponent_label(session: models.GameSession, user_id: int) -> str:
    """Chi c'era dall'altra parte: alias umano o etichetta del concorrente IA."""
    other = 1 if session.x_user_id == user_id else 0
    user = session.x_user if other == 0 else session.o_user
    if user is not None:
        return user.alias
    identity = ai_arena.identity_of(session, other)
    return ai_arena.label_of(identity) if identity else _("sconosciuto")


def _streaks(sessions, user_id: int) -> dict:
    best = current = 0
    for s in sessions:  # in ordine cronologico
        if _result_for(s, user_id) == "win":
            current += 1
            best = max(best, current)
        else:
            current = 0
    return {"best_win_streak": best, "current_win_streak": current}


def _phases(game, start_fen: str | None, history: list[str]) -> list[str] | None:
    """La fase di ogni semimossa (PRIMA che sia giocata); None se non si rigioca.

    Replay deterministico col motore puro: nessuna ricerca, solo la scacchiera
    per contare i pezzi e decidere apertura/mediogioco/finale.
    """
    state = game.from_fen(start_fen) if start_fen else game.initial_state()
    out: list[str] = []
    for uci in history:
        pieces = sum(1 for p in game.view_board(state) if p in _NONPAWN_PIECES)
        if pieces <= _ENDGAME_PIECES:
            out.append("endgame")
        else:
            out.append("opening" if len(out) < _OPENING_PLIES else "middlegame")
        move = next((m for m in game.legal_moves(state) if game.move_id(m) == uci), None)
        if move is None:
            return None
        state = game.apply(state, move)
    return out


def _acpl_score(acpl: float) -> int:
    """ACPL → punteggio 0-100 (lineare: 0 cp persi a mossa = 100, da 200 in su = 0)."""
    return round(max(0.0, 100.0 - acpl / 2))


def _aspects(sessions, user_id: int) -> dict | None:
    """Valutazione per i QUATTRO ASPETTI del gioco: aperture, tattica, strategia, finali.

    Materia prima: la perdita per mossa delle analisi GIÀ calcolate
    (``analysis_json``); le fasi arrivano da ``_phases``. Per aspetto:

    - **aperture** — ACPL delle proprie mosse nelle prime ~12 mosse, più
      l'aderenza al libro (quota di semimosse dentro una linea nota; solo
      partite dalla posizione iniziale standard);
    - **tattica** — blunder commessi e blunder avversari PUNITI (la propria
      risposta tiene il vantaggio regalato: perdita < ``_PUNISH_LOSS``); con
      le SOTTOCATEGORIE delle tattiche concesse (perdita ≥ ``_TACTIC_LOSS``):
      **matti mancati** (prima della mossa il motore vedeva un matto forzato
      per chi muove — |cp| ≥ ``_MATE_CP`` — e dopo non c'è più), **pezzi
      lasciati in presa** (la risposta avversaria è una cattura, taglie
      leggero/torre/donna dalla perdita), **scacchi concessi** (risposta di
      scacco senza cattura), **tattiche silenziose** (risposta quieta: le più
      difficili da vedere) e — trasversale — le **catture avvelenate** (la
      mossa che concede era essa stessa una cattura);
    - **strategia** — ACPL delle proprie mosse QUIETE del mediogioco (né
      catture né scacchi né promozioni: le scelte posizionali);
    - **finali** — ACPL delle proprie mosse giocate con al più
      ``_ENDGAME_PIECES`` pezzi (re e pedoni esclusi dal conto).

    I punteggi 0-100 sono euristici (v. ``_acpl_score``); sotto i campioni
    minimi il punteggio resta None ma i grezzi si riportano comunque.
    ``None`` se nessuna partita del giocatore è stata analizzata.
    """
    game = get_game(CHESS_CODE)
    buckets = {k: {"moves": 0, "loss": 0} for k in ("opening", "strategy", "endgame")}
    book_moves = book_eligible = 0
    blunders = opportunities = punished = 0
    sub = {
        "conceded": 0,
        "missed_mates": 0,
        "hanging": {"total": 0, "minor": 0, "rook": 0, "queen": 0},
        "check_tactics": 0,
        "quiet_tactics": 0,
        "poisoned_captures": 0,
    }
    analyzed = 0
    for s in reversed(sessions):  # dalla più recente, fino al tetto di replay
        if analyzed >= _ASPECT_GAMES:
            break
        if not s.analysis_json:
            continue
        try:
            data = json.loads(s.analysis_json)
        except ValueError:
            continue
        if data.get("status") != "done" or not data.get("evals"):
            continue
        moves = json.loads(s.moves_json or "[]")
        history = [m["id"] for m in moves if "id" in m]
        phases = _phases(game, s.start_fen, history)
        if phases is None:
            continue
        analyzed += 1
        side = "x" if s.x_user_id == user_id else "o"
        notation_by_ply = {m["ply"]: (m.get("notation") or "") for m in moves if "ply" in m}
        evals_by_ply = {e["ply"]: e for e in data["evals"] if "ply" in e}
        # Aderenza al libro: il prefisso noto più lungo della partita intera.
        book_len = 0
        if not s.start_fen:
            for _name, line in openings.all_lines():
                n = 0
                for a, b in zip(history, line):
                    if a != b:
                        break
                    n += 1
                book_len = max(book_len, n)
        for e in data["evals"]:
            ply = e.get("ply")
            if not ply or ply > len(phases):
                continue
            loss = min(int(e.get("loss") or 0), 1000)
            phase = phases[ply - 1]
            if e.get("by") != side:
                # Mossa avversaria: conta solo come occasione tattica da punire.
                if e.get("tag") == "??":
                    reply = evals_by_ply.get(ply + 1)
                    if reply is not None and reply.get("by") == side:
                        opportunities += 1
                        if min(int(reply.get("loss") or 0), 1000) < _PUNISH_LOSS:
                            punished += 1
                continue
            if e.get("tag") == "??":
                blunders += 1
            # Sottocategorie tattiche: cosa ho concesso davvero con questa mossa.
            raw_loss = int(e.get("loss") or 0)
            if raw_loss >= _TACTIC_LOSS:
                sub["conceded"] += 1
                if "x" in notation_by_ply.get(ply, ""):
                    sub["poisoned_captures"] += 1  # la mossa era essa stessa una cattura
                cp_prev = (evals_by_ply.get(ply - 1) or {}).get("cp")
                cp_now = e.get("cp")
                white = side == "x"
                had_mate = cp_prev is not None and (
                    cp_prev >= _MATE_CP if white else cp_prev <= -_MATE_CP
                )
                still_mate = cp_now is not None and (
                    cp_now >= _MATE_CP if white else cp_now <= -_MATE_CP
                )
                reply = notation_by_ply.get(ply + 1)
                if had_mate and not still_mate:
                    sub["missed_mates"] += 1
                elif reply and "x" in reply:
                    sub["hanging"]["total"] += 1
                    if raw_loss >= _HANG_QUEEN:
                        sub["hanging"]["queen"] += 1
                    elif raw_loss >= _HANG_ROOK:
                        sub["hanging"]["rook"] += 1
                    else:
                        sub["hanging"]["minor"] += 1
                elif reply and ("+" in reply or "#" in reply):
                    sub["check_tactics"] += 1
                elif reply:
                    sub["quiet_tactics"] += 1
                # Senza risposta (la partita è finita lì) la tattica resta
                # conteggiata fra le concesse ma non classificata.
            if phase == "opening":
                buckets["opening"]["moves"] += 1
                buckets["opening"]["loss"] += loss
                if not s.start_fen:
                    book_eligible += 1
                    if ply <= book_len:
                        book_moves += 1
            elif phase == "endgame":
                buckets["endgame"]["moves"] += 1
                buckets["endgame"]["loss"] += loss
            elif not any(c in notation_by_ply.get(ply, "") for c in "x+#="):
                buckets["strategy"]["moves"] += 1
                buckets["strategy"]["loss"] += loss
    if not analyzed:
        return None

    def _acpl(bucket: dict) -> float | None:
        return round(bucket["loss"] / bucket["moves"], 1) if bucket["moves"] else None

    acpl = {k: _acpl(b) for k, b in buckets.items()}
    scores = {
        k: _acpl_score(acpl[k]) if buckets[k]["moves"] >= _ASPECT_MIN_MOVES else None
        for k in buckets
    }
    book_rate = round(book_moves / book_eligible, 2) if book_eligible else None
    if scores["opening"] is not None and book_rate is not None:
        # Il libro pesa un quarto: conoscere la teoria aiuta, la precisione decide.
        scores["opening"] = round(0.75 * scores["opening"] + 25 * book_rate)
    per_game = round(blunders / analyzed, 2)
    tactics_score = None
    if analyzed >= _ASPECT_MIN_GAMES:
        avoid = max(0.0, 100.0 - per_game * 40)  # 0 blunder/partita = 100, 2,5+ = 0
        if opportunities:
            tactics_score = round((avoid + 100.0 * punished / opportunities) / 2)
        else:
            tactics_score = round(avoid)
    return {
        "games_analyzed": analyzed,
        "opening": {
            "moves": buckets["opening"]["moves"],
            "acpl": acpl["opening"],
            "book_rate": book_rate,
            "score": scores["opening"],
        },
        "tactics": {
            "blunders": blunders,
            "per_game": per_game,
            "opportunities": opportunities,
            "punished": punished,
            "score": tactics_score,
            "subcategories": sub,
        },
        "strategy": {
            "moves": buckets["strategy"]["moves"],
            "acpl": acpl["strategy"],
            "score": scores["strategy"],
        },
        "endgame": {
            "moves": buckets["endgame"]["moves"],
            "acpl": acpl["endgame"],
            "score": scores["endgame"],
        },
    }


def build(db: Session, user_id: int) -> dict | None:
    """Il cruscotto delle statistiche avanzate (None se l'utente non esiste)."""
    user = db.get(models.User, user_id)
    if user is None:
        return None
    current_season = rating.season(db)
    ratings = {r["game_code"]: r for r in rating.for_user(db, user_id, current_season)}

    per_game: list[dict] = []
    for score in user.scores:
        sessions = _user_sessions(db, user_id, score.game.code)
        entry = {
            "game_code": score.game.code,
            "game_name": score.game.name,
            "points": score.points,
            "wins": score.wins,
            "draws": score.draws,
            "losses": score.losses,
            "matches": score.matches_played,
            "elo": ratings.get(score.game.code),
            **_streaks(sessions, user_id),
        }
        per_game.append(entry)

    # Scacchi: esiti, badge e CADENZE dalle sessioni; il resto dal profilo in cache.
    chess_sessions = _user_sessions(db, user_id, CHESS_CODE)
    finish_reasons = {"mate": 0, "time": 0, "resign": 0, "agreement": 0, "repetition": 0}
    badges = dict.fromkeys(BADGE_SYMBOLS, 0)
    cadences: dict[str, dict] = {}
    my_marks = ("X", "O")
    for s in chess_sessions:
        # Prestazioni PER CADENZA (tc_category; None = senza orologio): rendimento
        # e — dove l'analisi esiste — precisione (ACPL delle proprie mosse).
        cat = s.tc_category or "none"
        row = cadences.setdefault(
            cat,
            {
                "category": cat,
                "games": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "analyzed": 0,
                "_loss_sum": 0,
                "_moves": 0,
            },
        )
        row["games"] += 1
        row[{"win": "wins", "draw": "draws", "loss": "losses"}[_result_for(s, user_id)]] += 1
        if s.analysis_json:
            try:
                analysis = json.loads(s.analysis_json)
            except ValueError:
                analysis = {}
            if analysis.get("status") == "done":
                side = "x" if s.x_user_id == user_id else "o"
                evals = [e for e in analysis.get("evals", []) if e.get("by") == side]
                if evals:
                    row["analyzed"] += 1
                    row["_moves"] += len(evals)
                    row["_loss_sum"] += sum(min(int(e.get("loss") or 0), 1000) for e in evals)
        reason = s.finish_reason or ("mate" if s.winner in ("x", "o") else "agreement")
        if s.winner == "draw" and s.finish_reason is None:
            reason = "agreement"  # patte di scacchiera senza motivo esplicito: raro
        finish_reasons[reason] = finish_reasons.get(reason, 0) + 1
        mark = "X" if s.x_user_id == user_id else "O"
        if mark not in my_marks:
            continue
        for move in json.loads(s.moves_json or "[]"):
            quality = move.get("quality")
            if quality and move.get("player") == mark and quality.get("symbol") in badges:
                badges[quality["symbol"]] += 1

    profile = profile_cache.get(db, user_id) or {}
    return {
        "user_id": user_id,
        "alias": user.alias,
        "season": current_season,
        "games": per_game,
        "chess": {
            "games": profile.get("games", 0),
            "by_color": profile.get("by_color"),
            "avg_plies": profile.get("avg_plies"),
            "quick_loss_rate": profile.get("quick_loss_rate"),
            "accuracy": profile.get("accuracy"),
            "finish_reasons": finish_reasons,
            "by_cadence": [
                {
                    "category": row["category"],
                    "games": row["games"],
                    "wins": row["wins"],
                    "draws": row["draws"],
                    "losses": row["losses"],
                    "analyzed": row["analyzed"],
                    "acpl": round(row["_loss_sum"] / row["_moves"], 1) if row["_moves"] else None,
                }
                # Ordine fisso di presentazione: dalla più lenta assenza di
                # orologio alle cadenze ufficiali.
                for key in ("none", "blitz", "rapid", "classical", "fide")
                if (row := cadences.get(key)) is not None
            ],
            "aspects": _aspects(chess_sessions, user_id),
            "badges": badges,
            "brilliancies": sum(badges.get(s, 0) for s in BRILLIANT),
        },
    }


def brilliancies(db: Session, user_id: int, limit: int = 30) -> list[dict]:
    """Le mosse coi badge 💎/🌟 giocate DALL'UTENTE, dalla più recente.

    Ogni voce porta ciò che serve alla galleria: notazione, avversario, data,
    la semimossa per lo screenshot (``board.png?ply=``) e per aprire la moviola
    sulla posizione esatta.
    """
    out: list[dict] = []
    for s in reversed(_user_sessions(db, user_id, CHESS_CODE)):
        mark = "X" if s.x_user_id == user_id else "O"
        for move in json.loads(s.moves_json or "[]"):
            quality = move.get("quality")
            if not quality or quality.get("symbol") not in BRILLIANT:
                continue
            if move.get("player") != mark:
                continue
            notation = move.get("notation") or ""
            piece = (
                notation[0]
                if notation[:1] in "KQRBN"
                else ("K" if notation.startswith("O-O") else "P")
            )
            out.append(
                {
                    "session_id": s.id,
                    "ply": move.get("ply"),
                    "symbol": quality.get("symbol"),
                    "piece": piece,
                    "notation": move.get("notation"),
                    "uci": move.get("id"),
                    "label": quality.get("label"),
                    "opponent": _opponent_label(s, user_id),
                    "game_name": s.game.name,
                    "date": (s.updated_at or s.created_at).isoformat()
                    if (s.updated_at or s.created_at)
                    else None,
                    "result": _result_for(s, user_id),
                }
            )
            if len(out) >= limit:
                return out
    return out
