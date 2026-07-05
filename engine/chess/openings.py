"""Libro delle aperture degli scacchi (in notazione UCI).

Usato per riconoscere il nome dell'apertura in corso e per far giocare l'IA secondo
linee note nelle prime mosse. Copre le principali aperture con le loro varianti
(linee più profonde per i sistemi più diffusi); ogni linea è validata dai test
rigiocandola col motore.

Il libro è estendibile senza toccare il codice: la variabile d'ambiente
``CHESS_BOOK_FILE`` può puntare a un file di testo con una linea per riga nel formato
``Nome apertura: e2e4 e7e5 g1f3 ...`` (``#`` per i commenti). Le mosse non valide
troncano la linea al primo errore quando il libro viene indicizzato.

Nota: il motore (``game.py``) indicizza queste linee **per posizione**, quindi le
continuazioni da libro valgono anche quando la posizione è raggiunta per trasposizione
(ordine di mosse diverso). Le linee duplicate o con prefissi comuni pesano la scelta:
più linee passano per una mossa, più spesso l'IA la gioca.
"""

from __future__ import annotations

import os
import random

# (nome, sequenza di mosse UCI). Le linee più profonde hanno la precedenza nel
# riconoscimento (vince il prefisso più lungo coerente con le mosse giocate).
OPENINGS: list[tuple[str, list[str]]] = [
    # ----- Prime mosse (nomi generici di ripiego) -----
    ("Apertura di Re", ["e2e4"]),
    ("Apertura di Donna", ["d2d4"]),
    ("Apertura Inglese", ["c2c4"]),
    ("Apertura Réti", ["g1f3"]),
    ("Apertura Bird", ["f2f4", "d7d5", "g1f3", "g8f6", "e2e3", "g7g6"]),
    ("Partita aperta", ["e2e4", "e7e5"]),
    # Linee-base con i nomi generici delle famiglie: precedono le varianti così, a
    # parità di profondità riconosciuta, vince il nome generico (più corretto finché
    # la variante non è ancora determinata).
    ("Partita Italiana", ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"]),
    ("Partita Spagnola (Ruy López)", ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"]),
    ("Partita Scozzese", ["e2e4", "e7e5", "g1f3", "b8c6", "d2d4"]),
    ("Difesa dei due cavalli", ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"]),
    ("Gambetto di Re", ["e2e4", "e7e5", "f2f4"]),
    ("Difesa Pirc", ["e2e4", "d7d6"]),
    ("Difesa Slava", ["d2d4", "d7d5", "c2c4", "c7c6"]),
    ("Gambetto di Donna rifiutato", ["d2d4", "d7d5", "c2c4", "e7e6"]),
    ("Difesa Est-Indiana", ["d2d4", "g8f6", "c2c4", "g7g6"]),
    ("Difesa Nimzo-Indiana", ["d2d4", "g8f6", "c2c4", "e7e6", "b1c3", "f8b4"]),
    ("Difesa Ovest-Indiana", ["d2d4", "g8f6", "c2c4", "e7e6", "g1f3", "b7b6"]),
    ("Difesa Olandese", ["d2d4", "f7f5"]),
    # ----- 1.e4 e5: partite aperte -----
    (
        "Partita Italiana (Giuoco Piano)",
        ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "c2c3", "g8f6", "d2d3", "d7d6"],
    ),
    (
        "Gambetto Evans",
        ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "b2b4", "c5b4", "c2c3", "b4a5", "d2d4"],
    ),
    (
        "Difesa dei due cavalli (attacco Ng5)",
        ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6", "f3g5", "d7d5", "e4d5", "c6a5"],
    ),
    (
        "Difesa dei due cavalli (moderna d3)",
        ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6", "d2d3", "f8c5"],
    ),
    (
        "Spagnola chiusa (Ruy López)",
        # fmt: off
        [
            "e2e4",
            "e7e5",
            "g1f3",
            "b8c6",
            "f1b5",
            "a7a6",
            "b5a4",
            "g8f6",
            "e1g1",
            "f8e7",
            "f1e1",
            "b7b5",
            "a4b3",
            "d7d6",
            "c2c3",
            "e8g8",
            "h2h3",
        ],
        # fmt: on
    ),
    (
        "Spagnola, difesa Berlinese",
        # fmt: off
        [
            "e2e4",
            "e7e5",
            "g1f3",
            "b8c6",
            "f1b5",
            "g8f6",
            "e1g1",
            "f6e4",
            "d2d4",
            "e4d6",
            "b5c6",
            "d7c6",
            "d4e5",
            "d6f5",
            "d1d8",
            "e8d8",
        ],
        # fmt: on
    ),
    (
        "Spagnola di cambio",
        ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5c6", "d7c6", "e1g1", "f7f6", "d2d4"],
    ),
    (
        "Spagnola aperta",
        # fmt: off
        [
            "e2e4",
            "e7e5",
            "g1f3",
            "b8c6",
            "f1b5",
            "a7a6",
            "b5a4",
            "g8f6",
            "e1g1",
            "f6e4",
            "d2d4",
            "b7b5",
            "a4b3",
            "d7d5",
            "d4e5",
            "c8e6",
        ],
        # fmt: on
    ),
    (
        "Partita Scozzese (variante Mieses)",
        # fmt: off
        [
            "e2e4",
            "e7e5",
            "g1f3",
            "b8c6",
            "d2d4",
            "e5d4",
            "f3d4",
            "g8f6",
            "d4c6",
            "b7c6",
            "e4e5",
            "d8e7",
            "d1e2",
            "f6d5",
            "c2c4",
        ],
        # fmt: on
    ),
    (
        "Partita Scozzese classica",
        # fmt: off
        [
            "e2e4",
            "e7e5",
            "g1f3",
            "b8c6",
            "d2d4",
            "e5d4",
            "f3d4",
            "f8c5",
            "c1e3",
            "d8f6",
            "c2c3",
            "g8e7",
        ],
        # fmt: on
    ),
    ("Gambetto Scozzese", ["e2e4", "e7e5", "g1f3", "b8c6", "d2d4", "e5d4", "f1c4"]),
    (
        "Difesa Petroff (Russa)",
        # fmt: off
        [
            "e2e4",
            "e7e5",
            "g1f3",
            "g8f6",
            "f3e5",
            "d7d6",
            "e5f3",
            "f6e4",
            "d2d4",
            "d6d5",
            "f1d3",
        ],
        # fmt: on
    ),
    (
        "Gambetto di Re accettato (Kieseritzky)",
        ["e2e4", "e7e5", "f2f4", "e5f4", "g1f3", "g7g5", "h2h4", "g5g4", "f3e5"],
    ),
    (
        "Gambetto di Re rifiutato",
        ["e2e4", "e7e5", "f2f4", "f8c5", "g1f3", "d7d6", "c2c3"],
    ),
    ("Partita Viennese", ["e2e4", "e7e5", "b1c3", "g8f6", "f2f4", "d7d5", "f4e5", "f6e4"]),
    (
        "Quattro cavalli (spagnola)",
        # fmt: off
        [
            "e2e4",
            "e7e5",
            "g1f3",
            "b8c6",
            "b1c3",
            "g8f6",
            "f1b5",
            "f8b4",
            "e1g1",
            "e8g8",
            "d2d3",
            "d7d6",
        ],
        # fmt: on
    ),
    (
        "Difesa Filidor",
        ["e2e4", "e7e5", "g1f3", "d7d6", "d2d4", "e5d4", "f3d4", "g8f6", "b1c3", "f8e7"],
    ),
    ("Partita del centro", ["e2e4", "e7e5", "d2d4", "e5d4", "d1d4", "b8c6", "d4e3"]),
    (
        "Gambetto Danese",
        ["e2e4", "e7e5", "d2d4", "e5d4", "c2c3", "d4c3", "f1c4", "c3b2", "c1b2"],
    ),
    # ----- Siciliana -----
    ("Difesa Siciliana", ["e2e4", "c7c5"]),
    (
        "Siciliana Najdorf",
        # fmt: off
        [
            "e2e4",
            "c7c5",
            "g1f3",
            "d7d6",
            "d2d4",
            "c5d4",
            "f3d4",
            "g8f6",
            "b1c3",
            "a7a6",
            "c1e3",
            "e7e5",
            "d4b3",
            "c8e6",
        ],
        # fmt: on
    ),
    (
        "Siciliana Dragone (attacco Jugoslavo)",
        # fmt: off
        [
            "e2e4",
            "c7c5",
            "g1f3",
            "d7d6",
            "d2d4",
            "c5d4",
            "f3d4",
            "g8f6",
            "b1c3",
            "g7g6",
            "c1e3",
            "f8g7",
            "f2f3",
            "e8g8",
            "d1d2",
            "b8c6",
        ],
        # fmt: on
    ),
    (
        "Siciliana classica (Richter-Rauzer)",
        # fmt: off
        [
            "e2e4",
            "c7c5",
            "g1f3",
            "d7d6",
            "d2d4",
            "c5d4",
            "f3d4",
            "g8f6",
            "b1c3",
            "b8c6",
            "c1g5",
        ],
        # fmt: on
    ),
    (
        "Siciliana Scheveningen",
        ["e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6", "b1c3", "e7e6"],
    ),
    (
        "Siciliana Sveshnikov",
        # fmt: off
        [
            "e2e4",
            "c7c5",
            "g1f3",
            "b8c6",
            "d2d4",
            "c5d4",
            "f3d4",
            "g8f6",
            "b1c3",
            "e7e5",
            "d4b5",
            "d7d6",
        ],
        # fmt: on
    ),
    ("Siciliana Taimanov", ["e2e4", "c7c5", "g1f3", "e7e6", "d2d4", "c5d4", "f3d4", "b8c6"]),
    ("Siciliana Kan", ["e2e4", "c7c5", "g1f3", "e7e6", "d2d4", "c5d4", "f3d4", "a7a6"]),
    (
        "Siciliana Alapin",
        ["e2e4", "c7c5", "c2c3", "g8f6", "e4e5", "f6d5", "d2d4", "c5d4", "g1f3"],
    ),
    (
        "Siciliana chiusa",
        ["e2e4", "c7c5", "b1c3", "b8c6", "g2g3", "g7g6", "f1g2", "f8g7", "d2d3", "d7d6"],
    ),
    ("Siciliana Rossolimo", ["e2e4", "c7c5", "g1f3", "b8c6", "f1b5", "g7g6"]),
    ("Siciliana Moscovita", ["e2e4", "c7c5", "g1f3", "d7d6", "f1b5", "c8d7"]),
    (
        "Siciliana, attacco Grand Prix",
        ["e2e4", "c7c5", "b1c3", "b8c6", "f2f4", "g7g6", "g1f3", "f8g7", "f1b5"],
    ),
    # ----- Francese -----
    ("Difesa Francese", ["e2e4", "e7e6"]),
    (
        "Francese, variante d'avanzata",
        ["e2e4", "e7e6", "d2d4", "d7d5", "e4e5", "c7c5", "c2c3", "b8c6", "g1f3", "d8b6"],
    ),
    (
        "Francese Tarrasch",
        ["e2e4", "e7e6", "d2d4", "d7d5", "b1d2", "c7c5", "e4d5", "e6d5", "g1f3"],
    ),
    (
        "Francese Winawer",
        # fmt: off
        [
            "e2e4",
            "e7e6",
            "d2d4",
            "d7d5",
            "b1c3",
            "f8b4",
            "e4e5",
            "c7c5",
            "a2a3",
            "b4c3",
            "b2c3",
            "g8e7",
        ],
        # fmt: on
    ),
    (
        "Francese classica",
        # fmt: off
        [
            "e2e4",
            "e7e6",
            "d2d4",
            "d7d5",
            "b1c3",
            "g8f6",
            "c1g5",
            "f8e7",
            "e4e5",
            "f6d7",
            "g5e7",
            "d8e7",
        ],
        # fmt: on
    ),
    ("Francese di cambio", ["e2e4", "e7e6", "d2d4", "d7d5", "e4d5", "e6d5", "f1d3"]),
    # ----- Caro-Kann -----
    ("Difesa Caro-Kann", ["e2e4", "c7c6"]),
    (
        "Caro-Kann classica",
        # fmt: off
        [
            "e2e4",
            "c7c6",
            "d2d4",
            "d7d5",
            "b1c3",
            "d5e4",
            "c3e4",
            "c8f5",
            "e4g3",
            "f5g6",
            "h2h4",
            "h7h6",
            "g1f3",
            "b8d7",
        ],
        # fmt: on
    ),
    (
        "Caro-Kann, variante d'avanzata",
        ["e2e4", "c7c6", "d2d4", "d7d5", "e4e5", "c8f5", "g1f3", "e7e6", "f1e2"],
    ),
    (
        "Caro-Kann di cambio",
        ["e2e4", "c7c6", "d2d4", "d7d5", "e4d5", "c6d5", "f1d3", "b8c6", "c2c3", "g8f6"],
    ),
    (
        "Caro-Kann, attacco Panov",
        # fmt: off
        [
            "e2e4",
            "c7c6",
            "d2d4",
            "d7d5",
            "e4d5",
            "c6d5",
            "c2c4",
            "g8f6",
            "b1c3",
            "e7e6",
            "g1f3",
        ],
        # fmt: on
    ),
    # ----- Altre difese su 1.e4 -----
    (
        "Difesa Scandinava",
        ["e2e4", "d7d5", "e4d5", "d8d5", "b1c3", "d5a5", "d2d4", "g8f6", "g1f3", "c8f5"],
    ),
    ("Scandinava moderna", ["e2e4", "d7d5", "e4d5", "g8f6", "d2d4", "f6d5", "g1f3"]),
    (
        "Difesa Alekhine",
        ["e2e4", "g8f6", "e4e5", "f6d5", "d2d4", "d7d6", "g1f3", "c8g4", "f1e2", "e7e6"],
    ),
    (
        "Difesa Pirc (attacco austriaco)",
        # fmt: off
        [
            "e2e4",
            "d7d6",
            "d2d4",
            "g8f6",
            "b1c3",
            "g7g6",
            "f2f4",
            "f8g7",
            "g1f3",
            "e8g8",
            "f1d3",
        ],
        # fmt: on
    ),
    ("Difesa Moderna", ["e2e4", "g7g6", "d2d4", "f8g7", "b1c3", "d7d6"]),
    # ----- 1.d4: giochi di donna -----
    ("Gambetto di Donna", ["d2d4", "d7d5", "c2c4"]),
    (
        "Gambetto di Donna rifiutato (ortodossa)",
        # fmt: off
        [
            "d2d4",
            "d7d5",
            "c2c4",
            "e7e6",
            "b1c3",
            "g8f6",
            "c1g5",
            "f8e7",
            "e2e3",
            "e8g8",
            "g1f3",
            "h7h6",
            "g5h4",
            "b7b6",
        ],
        # fmt: on
    ),
    (
        "Difesa Tarrasch",
        # fmt: off
        [
            "d2d4",
            "d7d5",
            "c2c4",
            "e7e6",
            "b1c3",
            "c7c5",
            "c4d5",
            "e6d5",
            "g1f3",
            "b8c6",
            "g2g3",
        ],
        # fmt: on
    ),
    (
        "Gambetto di Donna accettato",
        ["d2d4", "d7d5", "c2c4", "d5c4", "g1f3", "g8f6", "e2e3", "e7e6", "f1c4", "c7c5"],
    ),
    (
        "Difesa Slava",
        ["d2d4", "d7d5", "c2c4", "c7c6", "g1f3", "g8f6", "b1c3", "d5c4", "a2a4", "c8f5"],
    ),
    (
        "Difesa Semi-Slava",
        ["d2d4", "d7d5", "c2c4", "c7c6", "g1f3", "g8f6", "b1c3", "e7e6", "e2e3", "b8d7"],
    ),
    (
        "Apertura Catalana",
        # fmt: off
        [
            "d2d4",
            "g8f6",
            "c2c4",
            "e7e6",
            "g2g3",
            "d7d5",
            "f1g2",
            "f8e7",
            "g1f3",
            "e8g8",
            "e1g1",
        ],
        # fmt: on
    ),
    (
        "Sistema Londra",
        # fmt: off
        [
            "d2d4",
            "d7d5",
            "c1f4",
            "g8f6",
            "e2e3",
            "c7c5",
            "c2c3",
            "b8c6",
            "b1d2",
            "e7e6",
            "g1f3",
            "f8d6",
            "f4g3",
        ],
        # fmt: on
    ),
    ("Attacco Trompowsky", ["d2d4", "g8f6", "c1g5", "f6e4", "g5f4"]),
    ("Sistema Colle", ["d2d4", "d7d5", "g1f3", "g8f6", "e2e3", "e7e6", "f1d3", "c7c5", "c2c3"]),
    ("Attacco Torre", ["d2d4", "g8f6", "g1f3", "e7e6", "c1g5"]),
    # ----- Difese indiane -----
    (
        "Est-Indiana classica",
        # fmt: off
        [
            "d2d4",
            "g8f6",
            "c2c4",
            "g7g6",
            "b1c3",
            "f8g7",
            "e2e4",
            "d7d6",
            "g1f3",
            "e8g8",
            "f1e2",
            "e7e5",
            "e1g1",
            "b8c6",
            "d4d5",
            "c6e7",
        ],
        # fmt: on
    ),
    (
        "Est-Indiana, variante Sämisch",
        # fmt: off
        [
            "d2d4",
            "g8f6",
            "c2c4",
            "g7g6",
            "b1c3",
            "f8g7",
            "e2e4",
            "d7d6",
            "f2f3",
            "e8g8",
            "c1e3",
        ],
        # fmt: on
    ),
    (
        "Difesa Grünfeld",
        # fmt: off
        [
            "d2d4",
            "g8f6",
            "c2c4",
            "g7g6",
            "b1c3",
            "d7d5",
            "c4d5",
            "f6d5",
            "e2e4",
            "d5c3",
            "b2c3",
            "f8g7",
            "f1c4",
            "c7c5",
            "g1e2",
        ],
        # fmt: on
    ),
    (
        "Nimzo-Indiana (Rubinstein)",
        # fmt: off
        [
            "d2d4",
            "g8f6",
            "c2c4",
            "e7e6",
            "b1c3",
            "f8b4",
            "e2e3",
            "e8g8",
            "f1d3",
            "d7d5",
            "g1f3",
            "c7c5",
            "e1g1",
        ],
        # fmt: on
    ),
    (
        "Nimzo-Indiana classica",
        # fmt: off
        [
            "d2d4",
            "g8f6",
            "c2c4",
            "e7e6",
            "b1c3",
            "f8b4",
            "d1c2",
            "e8g8",
            "a2a3",
            "b4c3",
            "c2c3",
        ],
        # fmt: on
    ),
    (
        "Difesa Ovest-Indiana",
        # fmt: off
        [
            "d2d4",
            "g8f6",
            "c2c4",
            "e7e6",
            "g1f3",
            "b7b6",
            "g2g3",
            "c8b7",
            "f1g2",
            "f8e7",
            "e1g1",
            "e8g8",
            "b1c3",
            "f6e4",
        ],
        # fmt: on
    ),
    (
        "Benoni moderna",
        # fmt: off
        [
            "d2d4",
            "g8f6",
            "c2c4",
            "c7c5",
            "d4d5",
            "e7e6",
            "b1c3",
            "e6d5",
            "c4d5",
            "d7d6",
            "e2e4",
            "g7g6",
        ],
        # fmt: on
    ),
    ("Gambetto Benko", ["d2d4", "g8f6", "c2c4", "c7c5", "d4d5", "b7b5"]),
    (
        "Difesa Olandese classica",
        # fmt: off
        [
            "d2d4",
            "f7f5",
            "g2g3",
            "g8f6",
            "f1g2",
            "e7e6",
            "g1f3",
            "f8e7",
            "e1g1",
            "e8g8",
            "c2c4",
            "d7d6",
        ],
        # fmt: on
    ),
    (
        "Olandese Leningrado",
        ["d2d4", "f7f5", "g2g3", "g8f6", "f1g2", "g7g6", "g1f3", "f8g7", "e1g1", "e8g8"],
    ),
    # ----- Inglese e sistemi di fianchetto -----
    (
        "Inglese simmetrica",
        ["c2c4", "c7c5", "g1f3", "g8f6", "b1c3", "b8c6", "g2g3", "g7g6", "f1g2", "f8g7"],
    ),
    (
        "Inglese (siciliana in contromossa)",
        # fmt: off
        [
            "c2c4",
            "e7e5",
            "b1c3",
            "g8f6",
            "g1f3",
            "b8c6",
            "g2g3",
            "d7d5",
            "c4d5",
            "f6d5",
            "f1g2",
            "d5b6",
            "e1g1",
            "f8e7",
        ],
        # fmt: on
    ),
    (
        "Réti (sistema principale)",
        # fmt: off
        [
            "g1f3",
            "d7d5",
            "c2c4",
            "e7e6",
            "g2g3",
            "g8f6",
            "f1g2",
            "f8e7",
            "e1g1",
            "e8g8",
            "b2b3",
        ],
        # fmt: on
    ),
    ("Gambetto Réti accettato", ["g1f3", "d7d5", "c2c4", "d5c4", "e2e3"]),
    (
        "Attacco Est-Indiano",
        # fmt: off
        [
            "g1f3",
            "d7d5",
            "g2g3",
            "g8f6",
            "f1g2",
            "e7e6",
            "e1g1",
            "f8e7",
            "d2d3",
            "e8g8",
            "b1d2",
            "c7c5",
            "e2e4",
            "b8c6",
        ],
        # fmt: on
    ),
]


def _load_extra_lines() -> list[tuple[str, list[str]]]:
    """Linee aggiuntive da un file utente (``CHESS_BOOK_FILE``), se configurato.

    Formato: una linea per riga, ``Nome apertura: e2e4 e7e5 ...``; ``#`` commenta.
    Le righe malformate vengono ignorate; le mosse non valide vengono troncate al
    momento dell'indicizzazione per posizione (in ``chess.py``).
    """
    path = os.getenv("CHESS_BOOK_FILE")
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return []
    extra = []
    for row in raw.splitlines():
        row = row.strip()
        if not row or row.startswith("#") or ":" not in row:
            continue
        name, _, moves = row.partition(":")
        uci = moves.split()
        if name.strip() and uci:
            extra.append((name.strip(), uci))
    return extra


def all_lines() -> list[tuple[str, list[str]]]:
    """Libro completo: linee integrate + eventuali linee dal file utente."""
    return OPENINGS + _load_extra_lines()


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
    for name, line in all_lines():
        k = _common_prefix(history, line)
        if k >= 1 and (k == len(line) or k == len(history)) and k > best_len:
            best_name, best_len = name, k
    return best_name


def book_move(history: list[str]) -> str | None:
    """Una continuazione da libro per prefisso esatto di mosse.

    Nota: l'IA degli scacchi usa il libro **per posizione** (``Chess.opening_move``),
    che copre anche le trasposizioni; questa funzione resta per usi su sola history.
    """
    candidates = [
        line[len(history)]
        for _name, line in all_lines()
        if len(line) > len(history) and line[: len(history)] == history
    ]
    if not candidates:
        return None
    return random.choice(candidates)
