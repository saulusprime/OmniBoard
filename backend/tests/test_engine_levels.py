"""Livelli di difficoltà del motore locale (lati IA di tipo "ai").

Un livello scelto al setup calibra tempo di riflessione e jitter del motore
locale e SCAVALCA il provider remoto («Novizio» non significa Claude a piena
forza). La colonna è la stessa dei preset Stockfish (``*_ai_level``): il tipo
del lato distingue la semantica.
"""

from types import SimpleNamespace

from app import gameplay, ponder
from app.database import SessionLocal
from app.main import app
from app.opponents import local
from fastapi.testclient import TestClient


def _create(client, o_spec, alias):
    user = client.post(
        "/users",
        json={"first_name": "L", "last_name": "V", "alias": alias, "email": f"{alias}@e.it"},
    ).json()
    return client.post(
        "/sessions",
        json={"game_code": "chess", "x": {"type": "human", "user_id": user["id"]}, "o": o_spec},
    )


def test_create_with_engine_level():
    with TestClient(app) as client:
        resp = _create(client, {"type": "ai", "level": "novizio"}, "lvl_a")
        assert resp.status_code == 201
        view = resp.json()
        assert view["players"]["o"]["level"] == "novizio"
        assert view["players"]["o"]["level_label"] == "Novizio (per imparare)"
        # Il lato umano non ha livello né etichetta.
        assert view["players"]["x"]["level"] is None
        assert view["players"]["x"]["level_label"] is None


def test_unknown_level_rejected():
    with TestClient(app) as client:
        resp = _create(client, {"type": "ai", "level": "granmaestro"}, "lvl_b")
        assert resp.status_code == 400
        assert "sconosciuto" in resp.json()["detail"]


def test_level_and_provider_conflict():
    with TestClient(app) as client:
        resp = _create(client, {"type": "ai", "level": "medio", "provider": "qwen"}, "lvl_c")
        assert resp.status_code == 400


def _session(level=None, kind="ai"):
    return SimpleNamespace(
        x_is_ai=False,
        o_is_ai=True,
        x_ai_kind=None,
        o_ai_kind=kind,
        x_ai_level=None,
        o_ai_level=level,
    )


def test_engine_level_params_resolution():
    # Senza livello: parametri globali, jitter storico, provider ammesso.
    assert gameplay.engine_level_params(_session(), 1, 2000) == (2000, 15, True)
    # «Medio»: tempo e jitter del preset, provider scavalcato.
    assert gameplay.engine_level_params(_session("medio"), 1, 2000) == (500, 60, False)
    # «Maestro»: tempo globale (think_ms None nel preset), jitter zero, motore locale.
    assert gameplay.engine_level_params(_session("maestro"), 1, 2000) == (2000, 0, False)
    # Un livello sul lato Stockfish non è un livello del motore locale.
    assert gameplay.engine_level_params(_session("zeus", kind="stockfish"), 1, 2000) == (
        2000,
        15,
        True,
    )


def test_levels_are_ordered_and_labelled():
    presets = list(local.ENGINE_LEVELS.values())
    # Dal più forte al più debole: jitter non decrescente, tempo non crescente.
    jitters = [p["jitter"] for p in presets]
    assert jitters == sorted(jitters)
    times = [p["think_ms"] for p in presets if p["think_ms"] is not None]
    assert times == sorted(times, reverse=True)
    assert local.level_label("novizio") == "Novizio (per imparare)"
    assert local.level_label("zeus") is None
    assert local.level_label(None) is None


def test_ponder_skips_weak_levels(monkeypatch):
    """Il pondering non deve rinforzare un livello depotenziato con la TT."""
    monkeypatch.setenv("AI_ASYNC", "1")
    base = dict(
        id=987_654,
        status="in_progress",
        game=SimpleNamespace(code="chess"),
        x_is_ai=False,
        o_is_ai=True,
        x_ai_kind=None,
        o_ai_kind="ai",
        x_ai_level=None,
    )
    weak = SimpleNamespace(**base, o_ai_level="novizio")
    full = SimpleNamespace(**base, o_ai_level="maestro")
    with TestClient(app):
        db = SessionLocal()
        try:
            assert ponder.start(db, weak) is False
            # «Maestro» è piena forza: pondera come un lato senza livello.
            assert ponder.start(db, full) is True
        finally:
            ponder.drop(full.id)
            db.close()
