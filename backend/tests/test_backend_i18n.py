"""i18n dei DATI del backend: la risposta segue l'Accept-Language della richiesta."""

from app import i18n
from app.catalog_en import CATALOG_EN
from app.main import app
from fastapi.testclient import TestClient

EN = {"Accept-Language": "en"}


def test_parse_accept_language():
    assert i18n.parse_accept_language(None) == "it"
    assert i18n.parse_accept_language("en-US,en;q=0.9,it;q=0.5") == "en"
    assert i18n.parse_accept_language("fr-FR,de;q=0.8") == "it"  # non supportate → default
    assert i18n.parse_accept_language("it-IT") == "it"


def test_error_details_follow_language():
    with TestClient(app) as client:
        it = client.get("/sessions/999999")
        en = client.get("/sessions/999999", headers=EN)
        assert it.json()["detail"] == "Sessione non trovata"
        assert en.json()["detail"] == "Session not found"


def test_settings_labels_follow_language():
    with TestClient(app) as client:
        it = client.get("/admin/settings").json()
        en = client.get("/admin/settings", headers=EN).json()
        label_it = next(s["label"] for s in it if s["key"] == "scoring.points_win")
        label_en = next(s["label"] for s in en if s["key"] == "scoring.points_win")
        assert label_it == "Punti per una vittoria"
        assert label_en == "Points for a win"


def test_opening_name_translated_in_view():
    with TestClient(app) as client:
        u1 = client.post(
            "/users",
            json={"first_name": "I", "last_name": "N", "alias": "i18n_a", "email": "ia@e.it"},
        ).json()
        u2 = client.post(
            "/users",
            json={"first_name": "I", "last_name": "N", "alias": "i18n_b", "email": "ib@e.it"},
        ).json()
        sid = client.post(
            "/sessions",
            json={
                "game_code": "chess",
                "x": {"type": "human", "user_id": u1["id"]},
                "o": {"type": "human", "user_id": u2["id"]},
            },
        ).json()["id"]
        for uci in ["e2e4", "e7e5"]:
            client.post(f"/sessions/{sid}/move", json={"move": uci})
        it_view = client.get(f"/sessions/{sid}").json()
        en_view = client.get(f"/sessions/{sid}", headers=EN).json()
        assert it_view["opening"]  # 1.e4 e5 è nel libro
        # La versione inglese è ESATTAMENTE la traduzione a catalogo di quella italiana.
        assert en_view["opening"] == CATALOG_EN[it_view["opening"]]


def test_weakness_translation_preserves_numbers():
    from app.routers.users import _translate_weakness

    token = i18n.set_language("en")
    try:
        out = _translate_weakness("Precisione bassa: perde in media 145.5 centipedoni a mossa.")
        assert out == "Low accuracy: loses 145.5 centipawns per move on average."
        out = _translate_weakness("Rende meno con l'apertura «Difesa Siciliana».")
        assert out == "Performs worse in the «Sicilian Defence» opening."
        # Testo fisso: dal catalogo.
        out = _translate_weakness("Bilancio negativo: in generale tende a perdere.")
        assert out == "Negative record: tends to lose overall."
    finally:
        i18n.reset_language(token)


def test_default_language_is_italian_without_header():
    with TestClient(app) as client:
        resp = client.post("/auth/login", json={"identifier": "nessuno", "password": "x"})
        assert resp.json()["detail"] == "Credenziali non valide"
