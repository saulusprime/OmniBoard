"""Profilo scacchistico dell'avversario, ricavato dallo storico delle sue partite.

Analizza le partite di scacchi **concluse** di un giocatore per individuarne gli schemi
ricorrenti (aperture giocate, colore preferito) e le **debolezze** (aperture in cui rende
meno, fragilità tattica = sconfitte rapide, tendenza alla patta, eventuale debolezza nei
finali). Da queste ricava parametri di **stile** che il motore usa per adattare il gioco:

- ``aggression``: aumenta se l'avversario crolla presto (attaccare di più il suo re);
- ``contempt``: aumenta se l'avversario patta spesso (evitare le semplificazioni).

Il profilo è anche esposto via API per trasparenza (cosa l'IA ha "capito" dell'avversario).
"""

from __future__ import annotations

import json

from sqlalchemy import or_
from sqlalchemy.orm import Session

from engine.games import openings

from . import models

CHESS_CODE = "chess"
_QUICK_LOSS_PLIES = 30  # ~15 mosse: sconfitta "rapida" = fragilità tattica
_MIN_OPENING_GAMES = 2  # soglia minima per giudicare un'apertura


def _result_for(side: str, winner: str | None) -> str:
    if winner == "draw" or winner is None:
        return "draw"
    return "win" if winner == side else "loss"


def build_profile(db: Session, user_id: int, max_games: int = 200) -> dict | None:
    """Costruisce il profilo dell'avversario dalle sue partite di scacchi concluse.

    Ritorna ``None`` se l'utente non esiste; un profilo "vuoto" (stile neutro) se non ha
    ancora partite analizzabili.
    """
    user = db.get(models.User, user_id)
    if user is None:
        return None

    sessions = (
        db.query(models.GameSession)
        .join(models.Game)
        .filter(
            models.Game.code == CHESS_CODE,
            models.GameSession.status == "finished",
            or_(
                models.GameSession.x_user_id == user_id,
                models.GameSession.o_user_id == user_id,
            ),
        )
        .order_by(models.GameSession.id.desc())
        .limit(max_games)
        .all()
    )

    by_color = {
        "white": {"games": 0, "wins": 0, "draws": 0, "losses": 0},
        "black": {"games": 0, "wins": 0, "draws": 0, "losses": 0},
    }
    openings_agg: dict[str, dict] = {}
    total = wins = draws = losses = 0
    plies_sum = 0
    quick_losses = 0
    loss_plies_sum = 0

    for s in sessions:
        side = "x" if s.x_user_id == user_id else "o"
        color = "white" if side == "x" else "black"
        result = _result_for(side, s.winner)
        moves = json.loads(s.moves_json or "[]")
        plies = len(moves)
        name = openings.detect_opening([m["id"] for m in moves if "id" in m]) or "Sconosciuta"

        total += 1
        plies_sum += plies
        by_color[color]["games"] += 1
        by_color[color][result + "s" if result != "loss" else "losses"] += 1
        if result == "win":
            wins += 1
        elif result == "draw":
            draws += 1
        else:
            losses += 1
            loss_plies_sum += plies
            if plies <= _QUICK_LOSS_PLIES:
                quick_losses += 1

        agg = openings_agg.setdefault(name, {"name": name, "games": 0, "points": 0.0})
        agg["games"] += 1
        agg["points"] += 1.0 if result == "win" else (0.5 if result == "draw" else 0.0)

    profile = {
        "user_id": user_id,
        "alias": user.alias,
        "games": total,
        "by_color": by_color,
        "win_rate": round(wins / total, 3) if total else 0.0,
        "draw_rate": round(draws / total, 3) if total else 0.0,
        "loss_rate": round(losses / total, 3) if total else 0.0,
        "avg_plies": round(plies_sum / total, 1) if total else 0.0,
        "quick_loss_rate": round(quick_losses / total, 3) if total else 0.0,
        "avg_loss_plies": round(loss_plies_sum / losses, 1) if losses else 0.0,
    }

    openings_list = [
        {"name": o["name"], "games": o["games"], "score": round(o["points"] / o["games"], 3)}
        for o in openings_agg.values()
    ]
    openings_list.sort(key=lambda o: (-o["games"], o["name"]))
    profile["openings"] = openings_list
    profile["weakest_openings"] = [
        o["name"]
        for o in sorted(openings_list, key=lambda o: o["score"])
        if o["games"] >= _MIN_OPENING_GAMES and o["score"] < 0.5
    ][:3]

    profile["weaknesses"] = _weaknesses(profile)
    profile["style"] = _style(profile)
    return profile


def _weaknesses(p: dict) -> list[str]:
    out: list[str] = []
    if p["games"] < 3:
        return out  # troppe poche partite per concludere
    if p["quick_loss_rate"] >= 0.3:
        out.append("Fragilità tattica: subisce sconfitte rapide (attacchi diretti efficaci).")
    if p["draw_rate"] >= 0.4:
        out.append("Tende alla patta: conviene evitare le semplificazioni e tenere la tensione.")
    if p["loss_rate"] >= 0.5:
        out.append("Bilancio negativo: in generale tende a perdere.")
    if p["avg_loss_plies"] >= 70 and p["loss_rate"] >= 0.25:
        out.append("Debolezza nei finali: cede nelle partite lunghe.")
    for name in p["weakest_openings"]:
        out.append(f"Rende meno con l'apertura «{name}».")
    return out


def _style(p: dict) -> dict:
    """Parametri per il motore: più aggressivo contro chi crolla, più anti-patta contro
    chi pareggia spesso. Valori neutri (1.0 / 0) se i dati sono insufficienti."""
    if p["games"] < 3:
        return {"aggression": 1.0, "contempt": 0}
    aggression = round(1.0 + min(0.6, p["quick_loss_rate"]), 2)
    contempt = int(min(40, round(p["draw_rate"] * 60)))
    return {"aggression": aggression, "contempt": contempt}
