"""Corso di dama italiana: movimento, presa obbligatoria, promozione a dama.

Le pedine vivono solo sulle case scure; il bianco è in basso e muove verso
l'alto. Le coordinate sono le stesse degli scacchi (colonna a-h, riga 1-8).
"""

from __future__ import annotations

from . import path_task, pos8, sq, step

LESSONS = [
    {
        "code": "checkers-base",
        "game_code": "checkers",
        "title": "Le basi della dama",
        "order": 10,
        "steps": [
            step(
                "Nella dama si gioca solo sulle case scure. La pedina muove in "
                "DIAGONALE, in avanti, di una casella alla volta.",
                pos8({"e3": "⛀"}),
                highlights=[sq("d4"), sq("f4")],
                task=path_task("e3", "d4", "Muovi la pedina in avanti, da e3 a d4.", "Così!"),
            ),
            step(
                "La presa è OBBLIGATORIA: se una pedina avversaria è davanti a te "
                "in diagonale e la casa dietro è libera, DEVI saltarla e catturarla.",
                pos8({"e3": "⛀", "d4": "⛂"}),
                highlights=[sq("c5")],
                task=path_task("e3", "c5", "Salta la pedina nera: atterra in c5.", "Mangiata!"),
            ),
            step(
                "Le prese possono essere MULTIPLE: se dopo un salto puoi saltarne "
                "subito un'altra, continui nella stessa mossa. Qui la bianca "
                "salta due pedine in un colpo solo.",
                pos8({"e3": "⛀", "d4": "⛂", "d6": "⛂"}),
                highlights=[sq("c5"), sq("e7")],
                task=path_task("e3", "e7", "Doppia presa: da e3 fino a e7.", "Doppietta!"),
            ),
            step(
                "Quando una pedina raggiunge l'ultima riga viene promossa a DAMA "
                "(⛁): da quel momento può muovere e catturare anche all'indietro.",
                pos8({"a7": "⛀"}),
                highlights=[sq("b8")],
                task=path_task("a7", "b8", "Porta la pedina in b8 e diventa dama.", "Dama!"),
            ),
        ],
    },
]
