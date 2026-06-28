# Engine — Motore di gioco astratto

Pacchetto Python puro (nessuna dipendenza esterna) che definisce il modello astratto
di un gioco a turni per due giocatori a informazione perfetta, con *hook* per nodi del
caso (estensione futura: backgammon).

## Stato attuale

- [`core.py`](core.py) — interfaccia astratta `Game` (stato, mosse legali, applicazione
  mossa, terminalità, esito) + `Outcome`.

## Prossimi passi

- `engine/games/tictactoe.py` — prima implementazione concreta (Tris) per validare le
  primitive.
- Test unitari (`pytest`) del motore e dei giochi.
- A seguire: Forza 4, Dama italiana, Scacchi.

Il backend ([`../backend`](../backend)) userà questo pacchetto per validare le mosse e
gestire le partite.
