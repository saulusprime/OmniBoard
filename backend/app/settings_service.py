"""Registro e gestione dei parametri di configurazione del programma.

Tutti i parametri parametrizzabili sono definiti in ``SETTINGS_DEFS`` (tipo, default,
categoria, etichetta). I valori correnti sono persistiti nella tabella ``settings`` e
leggibili con :func:`get` (DB con fallback al default). Aggiungere un nuovo parametro =
aggiungere una voce qui e leggerlo con ``get`` dove serve; comparirà automaticamente
nell'interfaccia super admin.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from . import models

# Definizione di tutti i parametri configurabili (ordine = ordine in UI).
SETTINGS_DEFS = [
    {
        "key": "general.site_name",
        "type": "str",
        "default": "Scacchi",
        "category": "Generale",
        "label": "Nome del sito",
    },
    {
        "key": "users.allow_registration",
        "type": "bool",
        "default": True,
        "category": "Utenti",
        "label": "Consenti la registrazione di nuovi giocatori",
    },
    {
        "key": "scoring.points_win",
        "type": "float",
        "default": 3.0,
        "category": "Punteggio",
        "label": "Punti per una vittoria",
    },
    {
        "key": "scoring.points_draw",
        "type": "float",
        "default": 1.0,
        "category": "Punteggio",
        "label": "Punti per una patta",
    },
    {
        "key": "scoring.points_loss",
        "type": "float",
        "default": 0.0,
        "category": "Punteggio",
        "label": "Punti per una sconfitta",
    },
    {
        "key": "groups.min_votes_to_found",
        "type": "int",
        "default": 2,
        "category": "Gruppi",
        "label": "Voti minimi per fondare un gruppo",
    },
    {
        "key": "ai.move_delay_ms",
        "type": "int",
        "default": 700,
        "category": "IA",
        "label": "Ritardo prima della mossa dell'IA (millisecondi)",
    },
    {
        "key": "ai.provider",
        "type": "str",
        "default": "",
        "category": "IA",
        "label": "Provider IA attivo (vuoto = solo giocatore locale)",
    },
    {
        "key": "ai.engine_ms",
        "type": "int",
        "default": 2000,
        "category": "IA",
        "label": "Tempo di analisi del motore scacchi per mossa (millisecondi)",
    },
    {
        "key": "ai.async_moves",
        "type": "bool",
        "default": True,
        "category": "IA",
        "label": "Mosse IA in background (il client si aggiorna da solo; no = calcolo in linea)",
    },
    {
        "key": "ai.watch_pace_ms",
        "type": "int",
        "default": 1200,
        "category": "IA",
        "label": "Ritmo minimo tra le mosse IA osservate (IA-vs-IA e prima mossa; ms; 0 = nessuno)",
    },
    {
        "key": "stockfish.path",
        "type": "str",
        "default": "",
        "category": "Stockfish",
        "label": "Percorso del binario Stockfish (vuoto = STOCKFISH_PATH o ricerca nel PATH)",
    },
    {
        "key": "stockfish.move_ms",
        "type": "int",
        "default": 1000,
        "category": "Stockfish",
        "label": "Tempo di riflessione di Stockfish per mossa (millisecondi)",
    },
    {
        "key": "stockfish.elo",
        "type": "int",
        "default": 0,
        "category": "Stockfish",
        "label": "Elo simulato di Stockfish (0 = piena forza; range utile 1320-3190)",
    },
    {
        "key": "stockfish.skill_level",
        "type": "int",
        "default": 20,
        "category": "Stockfish",
        "label": "Skill Level di Stockfish (0-20, 20 = piena forza)",
    },
    {
        "key": "games.batch_max",
        "type": "int",
        "default": 1000,
        "category": "Giochi",
        "label": "Numero massimo di partite consecutive (batch IA-vs-IA)",
    },
    # Aspetto: letti dal frontend via GET /config (pubblico) a ogni pagina di gioco.
    {
        "key": "ui.anim_ms",
        "type": "int",
        "default": 250,
        "category": "Aspetto",
        "label": "Durata dell'animazione di spostamento dei pezzi (millisecondi; 0 = nessuna)",
    },
    {
        "key": "ui.sound_enabled",
        "type": "bool",
        "default": True,
        "category": "Aspetto",
        "label": "Effetto sonoro delle mosse",
    },
    {
        "key": "ui.sound_volume",
        "type": "int",
        "default": 40,
        "category": "Aspetto",
        "label": "Volume dell'effetto sonoro (0-100)",
    },
]

SETTINGS_BY_KEY = {d["key"]: d for d in SETTINGS_DEFS}

_TRUE = {"1", "true", "yes", "on", "si", "sì"}


def _cast(value: str, value_type: str):
    if value_type == "int":
        return int(value)
    if value_type == "float":
        return float(value)
    if value_type == "bool":
        return value.strip().lower() in _TRUE
    return value


def _to_str(value, value_type: str) -> str:
    if value_type == "bool":
        truthy = value.strip().lower() in _TRUE if isinstance(value, str) else bool(value)
        return "true" if truthy else "false"
    return str(value)


def get(db: Session, key: str):
    """Valore tipizzato del parametro: dal DB se presente, altrimenti il default."""
    definition = SETTINGS_BY_KEY.get(key)
    row = db.get(models.Setting, key)
    if row is not None:
        try:
            return _cast(row.value, row.value_type)
        except (ValueError, TypeError):
            pass
    return definition["default"] if definition else None


def get_all(db: Session) -> list[dict]:
    """Tutti i parametri (in ordine di registro) con valore corrente e default."""
    rows = {s.key: s for s in db.query(models.Setting).all()}
    result = []
    for d in SETTINGS_DEFS:
        row = rows.get(d["key"])
        value = _cast(row.value, row.value_type) if row else d["default"]
        result.append(
            {
                "key": d["key"],
                "category": d["category"],
                "label": d["label"],
                "type": d["type"],
                "value": value,
                "default": d["default"],
            }
        )
    return result


def update_many(db: Session, values: dict) -> list[str]:
    """Aggiorna i parametri indicati. Solleva ValueError su chiave/valore non validi."""
    updated = []
    for key, raw in values.items():
        definition = SETTINGS_BY_KEY.get(key)
        if not definition:
            raise ValueError(f"Parametro sconosciuto: {key}")
        try:
            _cast(str(raw), definition["type"])  # validazione del tipo
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Valore non valido per «{key}» (atteso {definition['type']})"
            ) from exc
        normalized = _to_str(raw, definition["type"])
        row = db.get(models.Setting, key)
        if row is None:
            row = models.Setting(
                key=key,
                category=definition["category"],
                label=definition["label"],
                value_type=definition["type"],
                value=normalized,
            )
            db.add(row)
        else:
            row.value = normalized
        updated.append(key)
    db.commit()
    return updated


def seed_settings(db: Session) -> None:
    """Inserisce i parametri mancanti e allinea i metadati (preservando i valori)."""
    for d in SETTINGS_DEFS:
        row = db.get(models.Setting, d["key"])
        if row is None:
            db.add(
                models.Setting(
                    key=d["key"],
                    category=d["category"],
                    label=d["label"],
                    value_type=d["type"],
                    value=_to_str(d["default"], d["type"]),
                )
            )
        else:
            row.category = d["category"]
            row.label = d["label"]
            row.value_type = d["type"]
    db.commit()
