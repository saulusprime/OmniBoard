"""Corso lampo di Tris: regole, vittoria e difesa (griglia 3×3, indici 0-8)."""

from __future__ import annotations

from . import cell_task, pos_grid, step

LESSONS = [
    {
        "code": "tictactoe-base",
        "game_code": "tictactoe",
        "title": "Imparare il Tris",
        "order": 10,
        "steps": [
            step(
                "Il Tris si gioca in due su una griglia 3×3: a turno si mette il "
                "proprio segno, vince chi allinea TRE segni (riga, colonna o "
                "diagonale). Il centro è la casella più forte: tocca a te!",
                pos_grid(3, 3, {}),
                highlights=[4],
                task=cell_task(4, "Gioca la prima mossa nel centro.", "Mossa migliore!"),
            ),
            step(
                "Quando hai DUE segni in fila e la terza casella è libera, chiudi "
                "subito: qui la tua fila in alto aspetta solo l'ultimo segno.",
                pos_grid(3, 3, {0: "X", 1: "X", 3: "O", 6: "O"}),
                highlights=[2],
                task=cell_task(2, "Completa il tris in alto a destra.", "Tris! Vittoria!"),
            ),
            step(
                "Difendersi conta quanto attaccare: se l'AVVERSARIO ha due segni "
                "in fila, devi bloccare la terza casella prima che chiuda lui.",
                pos_grid(3, 3, {0: "O", 1: "O", 4: "X"}),
                highlights=[2],
                task=cell_task(2, "Blocca la fila dell'avversario!", "Bloccato!"),
            ),
        ],
    },
]
