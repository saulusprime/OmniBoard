"""Preferenze estetiche per giocatore (opzioni utente).

A differenza dei parametri di programma (``settings_service``, globali e gestiti dal
super admin), queste sono scelte **personali** di ciascun giocatore, salvate nel campo
``User.prefs_json`` e modificabili dalla scheda giocatore senza alcun token:

- ``board_theme`` — tema di scacchiera e pezzi per scacchi e dama (colori delle case e
  dei pezzi, applicati dal client). Il backgammon NON è tematizzabile: usa sempre il
  tavolo classico con le punte triangolari.
- ``tris_mark`` — la forma del proprio segno nel Tris (al posto della classica X/O).

Aggiungere una preferenza = una voce in ``PREF_DEFS`` (+ il supporto lato client).
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from . import models

# Temi di scacchiera disponibili (chiave → etichetta). I colori vivono nel CSS del
# frontend (classi ``t-<chiave>``): qui si valida solo la scelta.
BOARD_THEMES = {
    "classico": "Classico (scuro)",
    "legno": "Legno (marrone/crema)",
    "smeraldo": "Smeraldo (verde/avorio)",
    "ghiaccio": "Ghiaccio (azzurro/grigio)",
}

# Forme ammesse per il segno del Tris. "" = default del lato (X oppure O).
TRIS_MARKS = ["X", "O", "✕", "✖", "★", "☆", "♥", "◆", "▲"]

# Default per le preferenze assenti.
_DEFAULTS = {"board_theme": "classico", "tris_mark": None}


def get_prefs(user: models.User | None) -> dict:
    """Preferenze effettive di un utente (con i default); vuote per i lati IA."""
    prefs = dict(_DEFAULTS)
    if user is not None:
        prefs.update({k: v for k, v in (user.prefs or {}).items() if k in _DEFAULTS})
    return prefs


def update_prefs(db: Session, user: models.User, values: dict) -> dict:
    """Valida e salva le preferenze indicate (le altre restano invariate).

    Solleva ``ValueError`` con un messaggio per l'utente se un valore non è ammesso.
    """
    current = user.prefs
    if "board_theme" in values:
        theme = values["board_theme"]
        if theme not in BOARD_THEMES:
            raise ValueError(f"Tema scacchiera sconosciuto (ammessi: {', '.join(BOARD_THEMES)})")
        current["board_theme"] = theme
    if "tris_mark" in values:
        mark = values["tris_mark"]
        if mark in ("", None):  # svuotare il campo = tornare al default del lato
            current.pop("tris_mark", None)
        elif mark not in TRIS_MARKS:
            raise ValueError(f"Segno del Tris non ammesso (ammessi: {' '.join(TRIS_MARKS)})")
        else:
            current["tris_mark"] = mark
    user.prefs_json = json.dumps(current)
    db.commit()
    return get_prefs(user)
