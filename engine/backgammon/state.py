"""Stato immutabile di una partita di Backgammon.

Rappresentazione:

- ``points``: 24 interi con segno, uno per punta. Positivo = pedine di X
  (giocatore 0), negativo = pedine di O (giocatore 1); 0 = punta vuota.
  X muove in direzione **decrescente** (23 → 0) e ha la casa nelle punte 0..5;
  O muove in direzione **crescente** (0 → 23) e ha la casa nelle punte 18..23.
- ``bar``: pedine colpite in attesa di rientro, per giocatore (X, O).
- ``off``: pedine già portate fuori, per giocatore (X, O). 15 = vittoria.
- ``current``: giocatore di turno (anche nei nodi del caso: è chi deve tirare).
- ``dice``: i dadi ancora da giocare in questo turno (un dado = una mossa di una
  pedina; un doppio vale quattro mosse). ``None`` = dadi da tirare → la partita è
  in un **nodo del caso** e le mosse legali sono assenti finché il server non
  estrae il tiro (vedi ``Game.apply_chance``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BackgammonState:
    points: tuple  # 24 interi con segno (positivo = X, negativo = O)
    bar: tuple  # (pedine X sulla barra, pedine O sulla barra)
    off: tuple  # (pedine X fuori, pedine O fuori)
    current: int  # giocatore di turno: 0 (X) o 1 (O)
    dice: tuple | None  # dadi residui del turno; None = da tirare (nodo del caso)
