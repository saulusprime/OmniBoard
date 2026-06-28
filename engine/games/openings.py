"""Libro delle aperture degli scacchi (in notazione UCI).

Usato per riconoscere il nome dell'apertura in corso e per far giocare l'IA secondo
linee note nelle prime mosse. Non è esaustivo: copre le aperture più comuni.
"""

from __future__ import annotations

import random

# (nome, sequenza di mosse UCI). Le linee più profonde hanno la precedenza nel
# riconoscimento (vince il prefisso più lungo coerente con le mosse giocate).
OPENINGS: list[tuple[str, list[str]]] = [
    ("Apertura di Re", ["e2e4"]),
    ("Apertura di Donna", ["d2d4"]),
    ("Apertura Inglese", ["c2c4"]),
    ("Apertura Réti", ["g1f3"]),
    ("Partita aperta", ["e2e4", "e7e5"]),
    ("Difesa Siciliana", ["e2e4", "c7c5"]),
    ("Difesa Francese", ["e2e4", "e7e6"]),
    ("Difesa Caro-Kann", ["e2e4", "c7c6"]),
    ("Difesa Scandinava", ["e2e4", "d7d5"]),
    ("Difesa Pirc", ["e2e4", "d7d6"]),
    ("Gambetto di Re", ["e2e4", "e7e5", "f2f4"]),
    ("Partita Italiana", ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"]),
    ("Difesa dei due cavalli", ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"]),
    ("Partita Spagnola (Ruy López)", ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"]),
    ("Partita Scozzese", ["e2e4", "e7e5", "g1f3", "b8c6", "d2d4"]),
    ("Difesa Petroff (Russa)", ["e2e4", "e7e5", "g1f3", "g8f6"]),
    ("Gambetto di Donna", ["d2d4", "d7d5", "c2c4"]),
    ("Difesa Slava", ["d2d4", "d7d5", "c2c4", "c7c6"]),
    ("Sistema Londra", ["d2d4", "d7d5", "c1f4"]),
    ("Difesa Est-Indiana", ["d2d4", "g8f6", "c2c4", "g7g6"]),
    ("Difesa Nimzo-Indiana", ["d2d4", "g8f6", "c2c4", "e7e6", "b1c3", "f8b4"]),
    ("Difesa Ovest-Indiana", ["d2d4", "g8f6", "c2c4", "e7e6", "g1f3", "b7b6"]),
]


def _common_prefix(a: list[str], b: list[str]) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def detect_opening(history: list[str]) -> str | None:
    """Nome dell'apertura: prefisso noto più lungo coerente con le mosse giocate."""
    best_name, best_len = None, 0
    for name, line in OPENINGS:
        k = _common_prefix(history, line)
        if k >= 1 and (k == len(line) or k == len(history)) and k > best_len:
            best_name, best_len = name, k
    return best_name


def book_move(history: list[str]) -> str | None:
    """Una continuazione da libro per la posizione corrente, se esiste."""
    candidates = [
        line[len(history)]
        for _name, line in OPENINGS
        if len(line) > len(history) and line[: len(history)] == history
    ]
    if not candidates:
        return None
    return random.choice(candidates)
