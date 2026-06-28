"""Test del profilo avversario (schemi/debolezze) e dell'adattamento di stile dell'IA."""

import json

from app import chess_profile, models
from app.database import SessionLocal
from app.main import app
from fastapi.testclient import TestClient


def _chess_game_id(db):
    return db.query(models.Game).filter_by(code="chess").first().id


def _add_user(db, alias):
    user = models.User(first_name="T", last_name="U", alias=alias, email=f"{alias}@e.it")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _add_finished_game(db, game_id, user_id, side, result, plies, move_id="e2e4"):
    """Crea una partita conclusa: ``side`` ∈ {'x','o'}, ``result`` ∈ {'win','draw','loss'}."""
    if result == "draw":
        winner = "draw"
    elif result == "win":
        winner = side
    else:
        winner = "o" if side == "x" else "x"
    moves = [
        {"ply": i + 1, "player": "X", "notation": "e2-e4", "id": move_id} for i in range(plies)
    ]
    s = models.GameSession(
        game_id=game_id,
        x_user_id=user_id if side == "x" else None,
        o_user_id=user_id if side == "o" else None,
        x_is_ai=side != "x",
        o_is_ai=side != "o",
        state_json="{}",
        moves_json=json.dumps(moves),
        status="finished",
        winner=winner,
    )
    db.add(s)
    db.commit()


def test_profile_none_for_missing_user():
    with TestClient(app):
        db = SessionLocal()
        try:
            assert chess_profile.build_profile(db, 999999) is None
        finally:
            db.close()


def test_empty_profile_is_neutral():
    with TestClient(app):
        db = SessionLocal()
        try:
            user = _add_user(db, "neutro")
            profile = chess_profile.build_profile(db, user.id)
            assert profile["games"] == 0
            assert profile["style"] == {"aggression": 1.0, "contempt": 0}
            assert profile["weaknesses"] == []
        finally:
            db.close()


def test_profile_detects_weaknesses_and_sets_style():
    with TestClient(app):
        db = SessionLocal()
        try:
            user = _add_user(db, "fragile")
            gid = _chess_game_id(db)
            # 3 sconfitte rapide (fragilità tattica) + 2 patte (tendenza al pari).
            for _ in range(3):
                _add_finished_game(db, gid, user.id, "x", "loss", plies=12)
            for _ in range(2):
                _add_finished_game(db, gid, user.id, "o", "draw", plies=40)

            profile = chess_profile.build_profile(db, user.id)
            assert profile["games"] == 5
            assert profile["quick_loss_rate"] == 0.6
            assert profile["draw_rate"] == 0.4
            # Stile: più aggressivo (crolla presto) e con contempt (patta spesso).
            assert profile["style"]["aggression"] > 1.4
            assert profile["style"]["contempt"] > 0
            text = " ".join(profile["weaknesses"])
            assert "tattica" in text.lower()
            assert "patta" in text.lower()
            # Tutte le partite hanno la stessa apertura (id ripetuto) → bersaglio debole.
            assert profile["weakest_openings"]
        finally:
            db.close()


def test_chess_profile_endpoint():
    with TestClient(app) as client:
        db = SessionLocal()
        try:
            user = _add_user(db, "apiprofile")
            uid = user.id
            gid = _chess_game_id(db)
            _add_finished_game(db, gid, uid, "x", "win", plies=50)
        finally:
            db.close()
        resp = client.get(f"/users/{uid}/chess-profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["games"] == 1
        assert "style" in data and "weaknesses" in data and "openings" in data
        assert client.get("/users/999999/chess-profile").status_code == 404
