"""Cache del profilo avversario: riuso, TTL, invalidazione a eventi."""

from app import profile_cache
from app.database import SessionLocal
from app.main import app
from fastapi.testclient import TestClient

FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]


def _user(client, alias):
    return client.post(
        "/users",
        json={"first_name": "P", "last_name": "R", "alias": alias, "email": f"{alias}@e.it"},
    ).json()


def test_cache_reuses_profile_and_invalidate_rebuilds(monkeypatch):
    from app import chess_profile

    calls = {"n": 0}
    vero = chess_profile.build_profile

    def contato(db, user_id, max_games=200):
        calls["n"] += 1
        return vero(db, user_id, max_games)

    monkeypatch.setattr(chess_profile, "build_profile", contato)
    with TestClient(app) as client:
        u = _user(client, "cache_a")
        profile_cache.invalidate()
        db = SessionLocal()
        try:
            primo = profile_cache.get(db, u["id"])
            secondo = profile_cache.get(db, u["id"])
            assert calls["n"] == 1  # seconda lettura: dalla cache
            assert secondo is primo  # stessa copia condivisa
            profile_cache.invalidate(u["id"])
            profile_cache.get(db, u["id"])
            assert calls["n"] == 2  # dopo l'invalidazione si ricostruisce
        finally:
            db.close()
        profile_cache.invalidate()


def test_ttl_zero_disables_cache(monkeypatch):
    from app import chess_profile, settings_service

    calls = {"n": 0}
    vero = chess_profile.build_profile

    def contato(db, user_id, max_games=200):
        calls["n"] += 1
        return vero(db, user_id, max_games)

    monkeypatch.setattr(chess_profile, "build_profile", contato)
    originale = settings_service.get

    def ttl_zero(db, key):
        return 0 if key == "profile.cache_ttl_s" else originale(db, key)

    monkeypatch.setattr(settings_service, "get", ttl_zero)
    with TestClient(app) as client:
        u = _user(client, "cache_b")
        profile_cache.invalidate()
        db = SessionLocal()
        try:
            profile_cache.get(db, u["id"])
            profile_cache.get(db, u["id"])
            assert calls["n"] == 2  # TTL 0: nessuna cache
        finally:
            db.close()


def test_finished_game_invalidates_profile():
    """Integrazione: la scheda profilo si aggiorna appena la partita finisce."""
    with TestClient(app) as client:
        u1, u2 = _user(client, "cache_c"), _user(client, "cache_d")
        profilo_prima = client.get(f"/users/{u1['id']}/chess-profile").json()
        base = profilo_prima["games"]

        sid = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": u1["id"]},
                "o": {"type": "human", "user_id": u2["id"]},
            },
        ).json()["id"]
        for uci in FOOLS_MATE:
            client.post(f"/sessions/{sid}/move", json={"move": uci})

        profilo_dopo = client.get(f"/users/{u1['id']}/chess-profile").json()
        # Senza l'invalidazione a eventi qui vedremmo ancora la copia in cache.
        assert profilo_dopo["games"] == base + 1
