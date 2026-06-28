# MEMORY — Diario tecnico e decisioni architetturali

> Diario tecnico del progetto **Scacchi**: andamento, traguardi, dettagli architetturali e
> scelte tecniche con le relative motivazioni. Complementare a [HANDOFF.md](./HANDOFF.md)
> (che è il registro cronologico delle sessioni). Le decisioni rilevanti sono annotate come
> *ADR* (Architecture Decision Record).
>
> **Ultimo aggiornamento:** 2026-06-28

---

## Modello concettuale del motore

Il cuore del progetto è un **motore di gioco astratto** che descrive in modo generico un
gioco a turni tra due giocatori. Le primitive previste:

- **GameState** — rappresentazione immutabile dello stato (configurazione del tavoliere,
  giocatore di turno, eventuali metadati come arrocco/en-passant negli scacchi).
- **Move** — una mossa applicabile a uno stato; applicarla produce un nuovo stato.
- **Generazione mosse legali** — dato uno stato, l'elenco delle mosse ammesse.
- **Condizione terminale ed esito** — vittoria/sconfitta/patta e relativo punteggio.
- **Nodo del caso (opzionale)** — punto in cui l'evoluzione dipende da un evento aleatorio
  (es. lancio di dadi), con una distribuzione di esiti. Riservato a giochi come backgammon.

Ogni **gioco concreto** (scacchi, dama, tris, forza 4) implementa queste primitive come
*plugin*. L'infrastruttura (backend, frontend, persistenza) lavora solo contro le primitive
astratte e non conosce le regole dei singoli giochi.

**Principi:**
- Logica **pura**: il motore non fa I/O (niente rete, niente DB, niente tempo reale) ed è
  quindi facilmente testabile in modo deterministico.
- Stato **immutabile**: applicare una mossa restituisce un nuovo stato, semplifica
  replay/undo e l'analisi.
- Validazione **lato motore**: la legalità di una mossa è decisa dal motore, mai dal client.

## Architettura a servizi

Tre livelli logici + database (vedi diagramma in [README.md](./README.md#architettura)):

1. **Frontend — Django**: presentazione. Template, rendering della scacchiera (JS/Canvas),
   gestione della sessione utente lato browser. Consuma le API del backend; non possiede dati
   di dominio.
2. **Backend — FastAPI**: API REST + WebSocket, orchestrazione delle partite, validazione
   delle mosse tramite il motore, persistenza, anagrafica, statistiche e ranking. Unica fonte
   di verità dei dati.
3. **Engine** — pacchetto Python puro indipendente dai framework.
4. **Database** — PostgreSQL (prod) / SQLite (sviluppo), di proprietà del backend.

**Flusso di una mossa (previsto):** il browser invia la mossa → Django la inoltra → FastAPI
la valida con il motore → se legale aggiorna lo stato, persiste la mossa e notifica
l'avversario via WebSocket → al termine registra l'esito e aggiorna le statistiche.

## Schema dati (bozza)

Tabelle previste lato backend (i dettagli saranno fissati con le migrazioni):

- **players** — `id`, `username`, `email`, `password_hash`, `created_at`, preferenze.
- **games** — catalogo dei tipi di gioco (`code`, `name`, `is_stochastic`).
- **matches** — `id`, `game_code`, `player_white`, `player_black`, `started_at`, `ended_at`,
  `result`, `winner`.
- **moves** — `id`, `match_id`, `ply`, `notation`, `state_after` (per replay/analisi).
- **statistics** — aggregati per (`player`, `game`): partite, vittorie, sconfitte, patte,
  ranking (Elo), serie.

## Decisioni architetturali (ADR)

### ADR-001 — Stack Python: Django (frontend) + FastAPI (backend) — 2026-06-28
**Contesto:** richiesta di un frontend web basato su Django e di un'interfaccia FastAPI verso
la backend, con database per statistiche e anagrafica.
**Decisione:** separare la presentazione (Django) dalla logica/API e dai dati (FastAPI +
database). Il motore è un pacchetto Python puro condiviso, usato dal backend.
**Conseguenze:** due servizi distinti; confine netto via API REST/WebSocket; il frontend non
accede direttamente al database di dominio. Maggiore separazione delle responsabilità a costo
di un confine di rete tra i due servizi.

### ADR-002 — Licenza MIT — 2026-06-28
**Contesto:** progetto open source destinato alla pubblicazione sul web.
**Decisione:** licenza **MIT** (permissiva, massima adozione e riuso).
**Conseguenze:** nessun obbligo di copyleft sulle modifiche; il trattamento dei dati degli
utenti è gestito separatamente dalla nota privacy in [LICENCE.md](./LICENCE.md).

### ADR-003 — Motore deterministico estendibile ai nodi del caso — 2026-06-28
**Contesto:** focus sui giochi deterministici (scacchi, dama, …) ma con interesse a includere
in futuro giochi con dadi.
**Decisione:** progettare il modello astratto deterministico-first, con *hook* espliciti per
nodi del caso, senza implementarli subito.
**Conseguenze:** complessità iniziale contenuta; backgammon/ludo restano abilitabili senza
riprogettare il motore.

### ADR-004 — Cambio di stack rispetto al prototipo precedente — 2026-06-28
**Contesto:** una sessione precedente (2026-06-27) aveva avviato un monorepo
TypeScript/React/Node-Express/Prisma con Dama italiana funzionante; quel codice non è presente
in cartella.
**Decisione:** ripartire da zero con lo stack Python descritto in ADR-001. I principi di gioco
(2 giocatori, estendibilità al caso, set di giochi) restano validi.
**Conseguenze:** il prototipo precedente è considerato storico (vedi [HANDOFF.md](./HANDOFF.md)).

### ADR-005 — Frontend Django senza database proprio — 2026-06-28
**Contesto:** il backend è l'unica fonte di verità dei dati; avere due ORM (Django + backend)
sugli stessi dati crea attrito.
**Decisione:** il frontend Django disattiva le app che richiedono un DB (auth, sessioni,
admin) e usa i messaggi su cookie; tutte le operazioni passano dal backend via HTTP
(`web/api_client.py`, httpx).
**Conseguenze:** nessun `migrate` da eseguire sul frontend; confine netto. L'autenticazione
sarà gestita lato backend e integrata in seguito.

### ADR-006 — Punteggi: schema provvisorio prima del rating — 2026-06-28
**Contesto:** servono punteggi per gioco e classifiche prima che il motore gestisca partite reali.
**Decisione:** punti semplici (vittoria +3, patta +1, sconfitta +0) registrati via
`POST /matches`; il punteggio universale è la somma su tutti i giochi; le classifiche per gioco
si filtrano per nazione/regione.
**Conseguenze:** facile da capire e testare; verrà sostituito da un rating (es. Elo) quando le
partite saranno gestite end-to-end dal motore. La tabella `moves` non è ancora introdotta.

### ADR-007 — Sessioni di gioco con stato persistito — 2026-06-28
**Contesto:** per giocare davvero serve mantenere lo stato di una partita tra le richieste.
**Decisione:** modello `GameSession` (stato serializzato dal motore in `state_json`, lati
X/O ciascuno umano o IA, stato in_progress/finished, vincitore). Il backend valida le mosse
col motore, fa giocare i lati IA in automatico e a fine partita assegna i punti (solo agli
umani) tramite `services`. Per il gioco umano-vs-umano si usa per ora la modalità *hotseat*
(due persone, stesso schermo); il gioco a distanza in tempo reale arriverà dopo.
**Conseguenze:** confine netto motore/persistenza; la logica punti è condivisa con `/matches`.

### ADR-008 — IA collegata a Qwen con fallback locale — 2026-06-28
**Contesto:** richiesta di un avversario IA collegato a Qwen.
**Decisione:** `ai.choose_move` interroga **Qwen** (DashScope, formato OpenAI-compatible) se
`QWEN_API_KEY` è impostata; valida la mossa e, se assente/non valida/non raggiungibile,
ripiega su un **minimax** locale ottimale (generico sull'interfaccia `Game`). La chiave è un
segreto: vive solo nel backend, mai nel frontend.
**Conseguenze:** il gioco è sempre giocabile anche senza chiave; per Tris il minimax è
imbattibile. In futuro si potrà differenziare la difficoltà.

### ADR-009 — Log mosse e storico; animazione IA lato client — 2026-06-28
**Contesto:** servono il log delle mosse, lo storico per giocatore e un'esperienza con la
mossa dell'IA mostrata con ritardo/animazione.
**Decisione:** il log è persistito in `GameSession.moves_json` (lista di {ply, player,
notation}); il motore fornisce `describe_move`. Lo storico è derivato dalle `GameSession`
concluse che coinvolgono l'utente (`GET /users/{id}/history`), quindi una stessa partita
appare nello storico di entrambi i giocatori senza duplicazioni. Il **ritardo e l'animazione**
della mossa IA sono lato **frontend** (JS: mossa umana subito, mossa IA dopo ~700ms con
animazione), evitando `sleep` nel backend (che rallenterebbe test e batch). Il form resta come
fallback senza JS.
**Conseguenze:** nessun blocco lato server; il backend resta veloce. Cambio di schema
(`moves_json`): senza Alembic, in sviluppo va eliminato il DB per ricrearlo.

## Traguardi

- **2026-06-28** — Definita l'architettura, scelti licenza e modello del motore; creata la
  base documentale e la configurazione GitHub.
- **2026-06-28** — Scaffold funzionante end-to-end: backend FastAPI (anagrafica, gruppi con
  fondazione tramite voto, punteggi, classifiche universale/per-gioco) + frontend Django di
  presentazione. Verificato via curl e form (CSRF). Scheletro del motore (`engine/core.py`).
- **2026-06-28** — Primo gioco giocabile: **Tris** (motore + sessioni persistite), con gioco
  umano-vs-umano, umano-vs-IA (**Qwen** + fallback minimax) e IA-vs-IA. Suite **pytest** (22
  test) e lint **ruff** (PEP8) introdotti come prassi.
- **2026-06-28** — Partite consecutive IA-vs-IA (batch) + **log mosse**, **storico per
  giocatore** e mossa IA con **ritardo/animazione** lato client. 27 test verdi.

## Questioni aperte

- Strategia di autenticazione tra Django e FastAPI (sessione vs token): da definire allo
  scaffold del backend.
- Scelta tra Django template + Canvas e un approccio più ricco lato client per la scacchiera.
- Formato di notazione delle mosse da persistere (specifico per gioco vs generico).
- ORM lato backend (SQLAlchemy) e gestione migrazioni con Alembic: da confermare.
