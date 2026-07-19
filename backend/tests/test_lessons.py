"""Test del tutorial (istruzione guidata): integrità dei contenuti e progressi.

Il test di integrità è il guardiano dei contenuti: ogni lezione aggiunta in
``app/lessons/`` viene controllata (griglia giusta, task dentro la scacchiera,
pezzo presente sull'origine, testi non vuoti) senza doverla provare a mano.
Il test di copertura del catalogo fa lo stesso per l'inglese: una lezione
nuova (o un testo ritoccato) senza traduzione fa fallire la suite.
"""

from app import lessons
from app.lessons import sq
from app.lessons.catalog_en import LESSONS_EN
from app.main import app
from fastapi.testclient import TestClient

TOKEN = "test-admin"  # impostato in conftest tramite ADMIN_TOKEN


def _student(client, alias="allievo"):
    user = client.post(
        "/users",
        json={
            "first_name": "P",
            "last_name": "R",
            "alias": alias,
            "email": f"{alias}@e.it",
            "password": "segretissima1",
        },
    ).json()
    client.post(f"/users/{user['id']}/approve", headers={"X-Admin-Token": TOKEN})
    out = client.post("/auth/login", json={"identifier": alias, "password": "segretissima1"}).json()
    return out["token"]


def test_every_lesson_is_well_formed():
    all_ = lessons.all_lessons()
    assert len(all_) >= 9  # corso scacchi (7) + dama + tris
    codes = [lesson["code"] for lesson in all_]
    assert len(codes) == len(set(codes)), "codici lezione duplicati"
    for lesson in all_:
        lessons.validate_lesson(lesson)


def test_lessons_catalog_en_covers_all_content():
    """Ogni stringa mostrata all'allievo ha la traduzione editoriale inglese."""
    for lesson in lessons.all_lessons():
        sources = [lesson["title"]]
        for s in lesson["steps"]:
            sources.append(s["text"])
            if s.get("task"):
                sources.extend([s["task"]["prompt"], s["task"]["success"]])
        for text in sources:
            where = f"{lesson['code']}: «{text[:40]}…»"
            assert text in LESSONS_EN, f"{where} senza traduzione in lessons/catalog_en.py"
            english = LESSONS_EN[text]
            assert english and english != text, f"{where} con traduzione vuota o identica"


def test_lessons_served_in_english_and_cache_stays_italian():
    """Accept-Language: en traduce titoli, passi e consegne; la cache resta italiana."""
    with TestClient(app) as client:
        en = {"Accept-Language": "en"}
        index = client.get("/lessons", headers=en).json()["lessons"]
        tris = next(le for le in index if le["code"] == "tictactoe-base")
        assert tris["title"] == "Learning Tic-Tac-Toe"

        pawn = client.get("/lessons/chess-pawn", headers=en).json()
        assert pawn["title"] == "The pawn"
        assert pawn["steps"][0]["text"].startswith("The pawn is the most numerous piece")
        assert pawn["steps"][0]["task"]["prompt"] == "Move the pawn one square, from e2 to e3."
        assert client.get("/lessons/nope", headers=en).json()["detail"] == "Lesson not found"

        # Stessa risorsa, richiesta successiva SENZA header: di nuovo italiana
        # (le copie tradotte non devono avvelenare la cache delle lezioni).
        pawn_it = client.get("/lessons/chess-pawn").json()
        assert pawn_it["title"] == "Il pedone"
        assert pawn_it["steps"][0]["text"].startswith("Il pedone è il pezzo più numeroso")


def test_coordinates_helper():
    assert sq("a8") == 0 and sq("h8") == 7
    assert sq("a1") == 56 and sq("h1") == 63
    assert sq("e2") == 52  # il pedone bianco di re


def test_index_and_lesson_endpoints():
    with TestClient(app) as client:
        index = client.get("/lessons").json()["lessons"]
        assert any(le["code"] == "chess-pawn" for le in index)
        assert all(le["progress"] is None for le in index)  # anonimo: nessun progresso

        lesson = client.get("/lessons/chess-pawn").json()
        assert lesson["rows"] == 8 and lesson["move_type"] == "chess"
        assert lesson["steps"][0]["task"]["kind"] == "path"
        assert client.get("/lessons/lezione-inesistente").status_code == 404


def test_progress_flow():
    with TestClient(app) as client:
        token = _student(client)
        # Anonimo: il salvataggio richiede l'accesso.
        assert client.post("/lessons/chess-pawn/progress", json={"step": 1}).status_code == 401

        # Avanzamento: il passo raggiunto non regredisce, completed è definitivo.
        client.post(
            "/lessons/chess-pawn/progress", json={"step": 2}, headers={"X-Auth-Token": token}
        )
        back = client.post(
            "/lessons/chess-pawn/progress", json={"step": 0}, headers={"X-Auth-Token": token}
        ).json()
        assert back["last_step"] == 2 and back["completed"] is False
        done = client.post(
            "/lessons/chess-pawn/progress",
            json={"step": 3, "completed": True},
            headers={"X-Auth-Token": token},
        ).json()
        assert done["completed"] is True

        # L'indice (autenticato) riporta il progresso; la lezione anche.
        index = client.get("/lessons", headers={"X-Auth-Token": token}).json()["lessons"]
        pawn = next(le for le in index if le["code"] == "chess-pawn")
        assert pawn["progress"] == {"last_step": 3, "completed": True}
        # Il passo viene comunque limitato alla lunghezza della lezione.
        clamped = client.post(
            "/lessons/tictactoe-base/progress",
            json={"step": 99},
            headers={"X-Auth-Token": token},
        ).json()
        assert clamped["last_step"] == 2  # la lezione ha 3 passi (0-based: max 2)
