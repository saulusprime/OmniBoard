"""Coda di lavoro delle mosse IA: dedup, cap di concorrenza, ripresa al riavvio."""

import threading
import time

from app import jobqueue
from app.database import SessionLocal
from app.main import app
from fastapi.testclient import TestClient


def _user(client, alias):
    return client.post(
        "/users",
        json={"first_name": "Q", "last_name": "J", "alias": alias, "email": f"{alias}@e.it"},
    ).json()


def _wait(cond, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_enqueue_dedups():
    jobqueue.reset_for_tests()
    assert jobqueue.enqueue(111_111) is True
    assert jobqueue.enqueue(111_111) is False  # già in coda: il polling non duplica
    assert jobqueue.is_scheduled(111_111) is True
    jobqueue.reset_for_tests()
    assert jobqueue.is_scheduled(111_111) is False


def test_worker_pool_respects_the_cap(monkeypatch):
    """Con 1 worker già avviato dai test precedenti o creato qui: mai 2 job attivi."""
    jobqueue.reset_for_tests()
    release = threading.Event()
    seen_active = []

    def slow(session_id):
        seen_active.append(jobqueue.snapshot()["active"])
        release.wait(timeout=5)

    monkeypatch.setattr(jobqueue, "_process", slow)
    jobqueue.start(1)  # idempotente: almeno un worker vivo
    workers = jobqueue.snapshot()["workers"]
    for sid in (222_201, 222_202, 222_203, 222_204):
        jobqueue.enqueue(sid)
    # I job attivi non superano MAI il numero di worker; gli altri aspettano.
    assert _wait(lambda: len(jobqueue.snapshot()["active"]) > 0)
    snap = jobqueue.snapshot()
    assert len(snap["active"]) <= workers
    assert len(snap["active"]) + len(snap["queued"]) == 4
    release.set()
    assert _wait(lambda: not jobqueue.snapshot()["active"] and not jobqueue.snapshot()["queued"])
    jobqueue.reset_for_tests()


def test_async_move_executed_by_the_pool(monkeypatch):
    """Partita vera: la risposta arriva senza la mossa IA, il worker la gioca dopo."""
    with TestClient(app) as client:
        u = _user(client, "coda_a")
        monkeypatch.setenv("AI_ASYNC", "1")
        jobqueue.reset_for_tests()
        jobqueue.start(1)
        sid = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": u["id"]},
                "o": {"type": "ai", "level": "novizio"},
            },
        ).json()["id"]
        before = client.post(f"/sessions/{sid}/move", json={"move": "0"}).json()
        assert len([c for c in before["board"] if c]) == 1  # solo la mossa umana
        # Il worker del pool gioca la risposta in background.
        assert _wait(
            lambda: len([c for c in client.get(f"/sessions/{sid}").json()["board"] if c]) >= 2
        )
        assert jobqueue.snapshot()["done"] >= 1
        monkeypatch.setenv("AI_ASYNC", "0")
        jobqueue.reset_for_tests()


def test_recovery_scan_resumes_stalled_ai_games(monkeypatch):
    """Riavvio del server: le partite al turno dell'IA ripartono senza client."""
    with TestClient(app) as client:
        u = _user(client, "coda_b")
        monkeypatch.setenv("AI_ASYNC", "1")
        jobqueue.reset_for_tests()
        # I worker del pool sono di processo e possono esistere già (ordine dei
        # test casuale): durante il setup il job NON deve essere lavorato.
        monkeypatch.setattr(jobqueue, "_process", lambda sid: None)
        sid = client.post(
            "/sessions",
            json={
                "game_code": "tictactoe",
                "x": {"type": "human", "user_id": u["id"]},
                "o": {"type": "ai", "level": "novizio"},
            },
        ).json()["id"]
        client.post(f"/sessions/{sid}/move", json={"move": "4"})
        jobqueue.reset_for_tests()  # come dopo un riavvio: coda persa
        db = SessionLocal()
        try:
            resumed = jobqueue.recovery_scan(db)  # il DB è la fonte di verità
        finally:
            db.close()
        assert resumed >= 1
        assert jobqueue.is_scheduled(sid) is True
        monkeypatch.setattr(jobqueue, "_process", jobqueue._default_process)
        jobqueue.start(1)
        assert _wait(
            lambda: len([c for c in client.get(f"/sessions/{sid}").json()["board"] if c]) >= 2
        )
        monkeypatch.setenv("AI_ASYNC", "0")
        jobqueue.reset_for_tests()


def test_admin_jobs_snapshot():
    with TestClient(app) as client:
        snap = client.get("/admin/jobs").json()
        assert {"workers", "queued", "active", "done", "errors"} <= set(snap)
