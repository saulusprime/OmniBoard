# Scacchi — Piattaforma universale per giochi da tavolo a turni

> Gioca a **scacchi** e a tutti gli altri giochi da tavolo a **turni e a informazione perfetta**
> (dama, tris, forza 4, …) tramite un unico motore astratto, direttamente dal browser.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENCE.md)
[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/stato-base%20documentale-orange.svg)](#stato-del-progetto)

> **Ultimo aggiornamento:** 2026-06-28 — *Login provider IA (Qwen, Claude, OpenAI) configurabili da super admin; quattro giochi giocabili (Tris, Forza 4, Dama, Scacchi).*

---

## Indice

- [Visione](#visione)
- [Caratteristiche principali](#caratteristiche-principali)
- [Giochi supportati](#giochi-supportati)
- [Architettura](#architettura)
- [Stack tecnologico](#stack-tecnologico)
- [Struttura del repository](#struttura-del-repository)
- [Dati raccolti](#dati-raccolti)
- [Requisiti](#requisiti)
- [Avvio rapido](#avvio-rapido)
- [Roadmap e TODO](#roadmap-e-todo)
- [Stato del progetto](#stato-del-progetto)
- [Documentazione correlata](#documentazione-correlata)
- [Come contribuire](#come-contribuire)
- [Licenza](#licenza)

---

## Visione

**Scacchi** è una piattaforma web open source per giocare in **due** a giochi da tavolo a
turni. L'idea portante è un **motore di gioco astratto** che modella in modo generico stato,
mosse legali e condizioni di vittoria: ogni gioco concreto (scacchi, dama, ecc.) è un
*plugin* che implementa questo modello. Aggiungere un nuovo gioco significa scrivere le sue
regole, non riscrivere l'infrastruttura.

Il progetto nasce attorno agli **scacchi** come gioco di riferimento, ma è progettato fin
dall'inizio per ospitare l'intera famiglia dei giochi a **informazione perfetta** e, in
prospettiva, anche quelli con **nodi del caso** (dadi) come backgammon e ludo.

## Caratteristiche principali

- ♟️ **Motore astratto unico** condiviso da tutti i giochi (logica pura, testabile, senza I/O).
- 🎲 **Deterministico + estendibile al caso**: il modello prevede *hook* per nodi stocastici
  (dadi), così da poter aggiungere in futuro backgammon e ludo.
- 🌐 **Esperienza web** con interfaccia grafica della scacchiera e gioco in tempo reale.
- 👤 **Anagrafica giocatori** e profili.
- 📊 **Statistiche di gioco** per giocatore e per gioco (partite, vittorie, ranking).
- 🧩 **Architettura a servizi**: presentazione (Django) separata dalla logica/API (FastAPI).
- 🤖 **Avversario IA** multi-provider (**Qwen**, **Claude/Anthropic**, **OpenAI**): i token si
  configurano da una pagina **«Provider IA»** del super admin (salvati lato server, non nel
  `.env`), con fallback locale (minimax alpha-beta) e mossa mostrata con ritardo e animazione.
- ♟️ **Scacchi completi** (arrocco, en passant, promozione, matto/stallo) con **libro di
  aperture** (Italiana, Siciliana, Scozzese, Spagnola…): l'apertura viene riconosciuta e l'IA
  la segue.
- 🧠 **Motore scacchi forte**: ricerca alpha-beta con *iterative deepening*, *transposition
  table*, *quiescence* (niente pezzi regalati) e valutazione posizionale ricca; trova matti e
  combinazioni forzate. Budget di tempo per mossa configurabile.
- 🕵️ **Modello dell'avversario**: l'IA analizza lo **storico** delle partite del giocatore
  (aperture, fragilità tattica, tendenza alla patta, finali) per individuarne schemi e debolezze
  e **adatta** il proprio stile (più aggressiva con chi crolla, anti-patta con chi pareggia).
- 📜 **Log delle mosse** di ogni partita, salvato nello **storico di entrambi i giocatori**.
- 🛠️ **Tutto parametrizzabile** da un'interfaccia **super admin**: punteggi, regole gruppi,
  registrazione utenti, ritardo IA, limiti, ecc. (protetta da token).
- 🔓 **Open source** con licenza [MIT](./LICENCE.md).

## Giochi supportati

Lo stato di implementazione è indicativo della *roadmap*; in questa fase il repository
contiene la sola base documentale.

| Gioco        | Tipo                 | Stato        |
|--------------|----------------------|--------------|
| Tris         | Deterministico       | ✅ Giocabile (umano e IA) |
| Forza 4      | Deterministico       | ✅ Giocabile (umano e IA) |
| Dama italiana| Deterministico       | ✅ Giocabile (umano e IA) |
| Scacchi ♟️    | Deterministico       | ✅ Giocabile (umano e IA, con libro aperture) |
| Backgammon   | Con nodi del caso 🎲  | 🧪 Futuro      |

I giochi più semplici (tris, forza 4, dama) servono a validare le primitive del motore prima
di affrontare la complessità degli scacchi. Le regole di ciascun gioco sono documentate in
[MANUAL.md](./MANUAL.md).

## Architettura

La piattaforma è organizzata in tre livelli logici più il database:

```text
        ┌──────────────────────────────────────────────────────────────┐
        │                          BROWSER                               │
        │           UI scacchiera · lobby · profilo · statistiche        │
        └───────────────▲───────────────────────────────┬──────────────┘
                        │ HTML / static / JS             │ WebSocket (mosse live)
                        │                                 │
        ┌───────────────┴─────────────────┐              │
        │   FRONTEND — Django              │              │
        │   • template e viste            │              │
        │   • rendering scacchiera        │              │
        │   • sessione utente / UI login  │              │
        └───────────────┬─────────────────┘              │
                        │ REST (HTTP) + WebSocket         │
                        ▼                                 ▼
        ┌──────────────────────────────────────────────────────────────┐
        │   BACKEND — FastAPI                                            │
        │   • API REST + WebSocket                                       │
        │   • orchestrazione partite e validazione mosse                 │
        │   • anagrafica giocatori, statistiche, ranking                 │
        │            │                              │                    │
        │            ▼                              ▼                    │
        │   ┌─────────────────┐          ┌────────────────────────┐     │
        │   │  GAME ENGINE     │          │   DATABASE             │     │
        │   │  (pacchetto      │          │   players · matches ·  │     │
        │   │   Python puro)   │          │   moves · statistics   │     │
        │   │  scacchi, dama,  │          │   (PostgreSQL / SQLite)│     │
        │   │  tris, forza4 …  │          └────────────────────────┘     │
        │   └─────────────────┘                                         │
        └──────────────────────────────────────────────────────────────┘
```

**Responsabilità dei componenti:**

- **Frontend (Django)** — livello di presentazione. Serve le pagine web, disegna la
  scacchiera interattiva, gestisce la sessione utente lato browser e consuma le API del
  backend. Non possiede i dati di dominio.
- **Backend (FastAPI)** — interfaccia verso la *backend* e cuore della logica applicativa.
  Espone API REST e WebSocket, valida le mosse tramite il motore, persiste partite e
  statistiche, gestisce l'anagrafica e i ranking. È l'unica fonte di verità dei dati.
- **Game engine** — pacchetto Python puro, indipendente dai framework, che definisce il
  modello astratto di gioco (stato, mosse, generazione mosse legali, condizioni terminali,
  esito) con supporto opzionale a nodi del caso. I singoli giochi sono implementazioni di
  questo modello. Completamente coperto da unit test, senza dipendenze da I/O.
- **Database** — conserva anagrafica giocatori, partite, storico mosse e statistiche.
  PostgreSQL in produzione, SQLite in sviluppo.

> Le decisioni architetturali e le relative motivazioni sono tracciate in [MEMORY.md](./MEMORY.md).

## Stack tecnologico

| Livello        | Tecnologia                                  |
|----------------|---------------------------------------------|
| Frontend/web   | **Django** (template + JS/Canvas per la scacchiera) |
| API/backend    | **FastAPI** (REST + WebSocket)              |
| Motore         | **Python** puro (nessuna dipendenza da framework) |
| Persistenza    | **PostgreSQL** (prod) · **SQLite** (sviluppo) |
| Migrazioni     | Alembic (lato backend)                       |
| Test           | pytest                                        |
| Qualità codice | ruff (lint + format)                          |
| Linguaggio doc | Italiano                                      |

## Struttura del repository

```text
Scacchi/
├── README.md / HANDOFF.md / MEMORY.md / MANUAL.md / LICENCE.md   # documentazione
├── CONTRIBUTING.md / CODE_OF_CONDUCT.md / SECURITY.md            # community
├── Makefile             # comandi di sviluppo (install / backend / frontend)
├── .github/             # configurazione GitHub (CI, template issue/PR, dependabot)
├── .env.example         # variabili d'ambiente di esempio
│
├── engine/              # motore di gioco (pacchetto Python puro, una directory per gioco)
│   ├── common/          # parti condivise: una classe per file
│   │   ├── game.py      #   interfaccia astratta Game (con hook per nodi del caso)
│   │   ├── outcome.py   #   esito di una partita (Outcome)
│   │   └── registry.py  #   registro dei giochi disponibili
│   ├── tictactoe/       # Tris: game.py (regole) + state.py (stato)
│   ├── connect4/        # Forza 4: game.py + state.py
│   ├── draughts/        # Dama italiana: game.py + state.py
│   ├── chess/           # Scacchi:
│   │   ├── game.py      #   regole (classe Chess)
│   │   ├── state.py     #   stato immutabile (ChessState)
│   │   ├── board.py     #   scacchiera: costanti e funzioni di base
│   │   ├── engine.py    #   motore di ricerca (alpha-beta, quiescence, TT)
│   │   ├── context.py   #   contesto di ricerca (SearchContext)
│   │   ├── errors.py    #   eccezioni del motore (TimeUp)
│   │   └── openings.py  #   libro delle aperture
│   └── tests/           # test del motore e dei giochi
│
├── backend/             # servizio FastAPI + accesso al database
│   └── app/
│       ├── main.py      # app FastAPI (create_all + seed + router)
│       ├── models.py    # modelli SQLAlchemy (utenti, giochi, punteggi, gruppi)
│       ├── schemas.py   # schemi Pydantic
│       ├── gameplay.py  # svolgimento partite + worker IA in background
│       └── routers/     # users, games, groups, matches, rankings, sessions, admin
│
└── frontend/            # progetto Django (presentazione, nessun DB proprio)
    ├── scacchi_web/     # settings, urls, wsgi/asgi
    └── web/             # views, forms, api_client (HTTP→backend), templates
```

Convenzione del motore: **una directory per gioco** (`engine/<gioco>/`), le parti comuni in
`engine/common/`, **una classe per file** (regole in `game.py`, stato in `state.py`).
Aggiungere un gioco = creare una nuova directory con `game.py`/`state.py` e registrarlo in
`engine/common/registry.py`.

## Dati raccolti

Il database è pensato per raccogliere, nel rispetto della normativa (vedi nota privacy in
[LICENCE.md](./LICENCE.md)):

- **Anagrafica giocatori** — identificativo, username, credenziali (hash), data di
  registrazione e preferenze.
- **Partite (matches)** — gioco, partecipanti, data/ora, esito, durata.
- **Storico mosse (moves)** — sequenza delle mosse per ogni partita (per replay/analisi).
- **Statistiche** — partite giocate/vinte/perse/patte per giocatore e per gioco, ranking
  (es. Elo), serie di vittorie.

## Requisiti

- Python 3.12+
- PostgreSQL (in produzione) — SQLite è sufficiente per lo sviluppo
- (Frontend) un browser moderno

> Le istruzioni dettagliate di installazione e avvio verranno aggiunte qui non appena lo
> scaffold del codice sarà presente.

## Avvio rapido

Servono Python 3.12+. I due servizi (backend e frontend) si avviano in due terminali.
Con il `Makefile` di comodo:

```bash
make install        # crea .venv e installa le dipendenze di backend e frontend
make backend        # terminale 1 → FastAPI su http://127.0.0.1:8000  (/docs per l'API)
make frontend       # terminale 2 → Django  su http://127.0.0.1:8001
```

In alternativa, manualmente:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt -r frontend/requirements.txt

# terminale 1 — backend
cd backend && uvicorn app.main:app --reload --port 8000

# terminale 2 — frontend
python frontend/manage.py runserver 8001
```

Apri <http://127.0.0.1:8001/>. Il backend crea/aggiorna automaticamente lo schema SQLite
(`backend/scacchi.db`) e popola il catalogo dei giochi al primo avvio. Il frontend non usa
database. Configurazione tramite `.env` (vedi `.env.example`).

## Roadmap e TODO

- [x] Base documentale del progetto (README, HANDOFF, MEMORY, MANUAL, LICENCE)
- [x] Configurazione GitHub (CI, template issue/PR, dependabot, contributing, code of conduct, security)
- [x] Scaffold backend FastAPI (`backend/`) + schema database (SQLAlchemy/SQLite)
- [x] Scaffold frontend Django (`frontend/`) — interfaccia web e menu
- [x] Anagrafica giocatori (nome, cognome, alias, email, nazionalità, regione)
- [x] Gruppi: fondazione tramite proposta + voto (soglia ≥ 2)
- [x] Punteggi per gioco + classifica universale + classifiche per gioco (globale/nazionale/regionale)
- [x] Interfaccia **super admin**: parametri di programma configurabili (punteggi, regole, IA, limiti)
- [x] Scheletro del motore astratto (`engine/common/game.py`)
- [x] Primo gioco giocabile: **Tris** (motore + sessioni di gioco persistite)
- [x] Avversario **IA (Qwen)** con fallback locale (minimax completo per Tris, a profondità + euristica per Forza 4)
- [x] Secondo gioco giocabile: **Forza 4** (scacchiera generica nel frontend)
- [x] Terzo gioco giocabile: **Dama italiana** (catture obbligatorie, dame, mosse a percorso)
- [x] Quarto gioco giocabile: **Scacchi** completi + **libro di aperture** (riconoscimento + IA)
- [x] **Login provider IA** (Qwen, Claude, OpenAI): token configurabili da super admin, salvati lato server
- [x] **IA scacchi potenziata**: motore alpha-beta dedicato (quiescence, TT) + **modello dell'avversario** (schemi/debolezze dallo storico)
- [x] **Mosse IA in background**: risposta immediata, l'IA pensa in un worker e il client si aggiorna via polling
- [ ] Autenticazione/login dei giocatori
- [ ] Regole di gestione dei gruppi (ruoli, inviti, espulsioni)
- [ ] Migrazioni del database (Alembic) e PostgreSQL in produzione
- [ ] Aggiornamento in tempo reale della partita (WebSocket / polling) per il gioco a distanza
- [ ] Affinamento regole dama (priorità FID tra catture di pari numero, patte)
- [ ] Scacchi: patta per ripetizione; ampliamento del libro aperture; apertura-bersaglio sul profilo avversario
- [ ] Sistema di rating (es. Elo) al posto dello schema punti provvisorio
- [ ] (Futuro) supporto nodi del caso → Backgammon

## Stato del progetto

🟢 **Quattro giochi giocabili.** Backend FastAPI e frontend Django girano end-to-end: si possono
creare giocatori, fondare gruppi tramite voto, consultare le classifiche e **giocare a Tris,
Forza 4, Dama italiana e Scacchi** (umano vs umano in locale, umano vs IA, IA vs IA — con la possibilità di simulare **N partite
consecutive** IA-vs-IA, es. 100). L'IA può usare un **provider remoto** (Qwen, Claude o OpenAI),
con token configurabili dalla pagina super admin «Provider IA», e ripiega sul giocatore locale
ottimale; la sua mossa appare con un piccolo ritardo e animazione. Ogni partita ha un **log delle mosse**
(widget in pagina) salvato nello **storico di entrambi i giocatori**. A fine partita i punteggi
si aggiornano in automatico. I parametri di programma (punteggi, regole, ecc.) sono modificabili
da un'**interfaccia super admin**. Mancano autenticazione dei giocatori, gioco a distanza in
tempo reale e gli altri giochi.

## Documentazione correlata

- [HANDOFF.md](./HANDOFF.md) — storico delle sessioni di lavoro.
- [MEMORY.md](./MEMORY.md) — diario tecnico e decisioni architetturali.
- [MANUAL.md](./MANUAL.md) — manuale dei giochi e dell'applicazione.
- [TODO.md](./TODO.md) — backlog delle idee di potenziamento e miglioramento.
- [CONTRIBUTING.md](./CONTRIBUTING.md) — come contribuire.
- [LICENCE.md](./LICENCE.md) — licenza e nota sul trattamento dei dati.

## Come contribuire

I contributi sono benvenuti! Leggi [CONTRIBUTING.md](./CONTRIBUTING.md) e il
[Codice di Condotta](./CODE_OF_CONDUCT.md). Per segnalare una vulnerabilità di sicurezza
consulta [SECURITY.md](./SECURITY.md).

## Licenza

Distribuito con licenza **MIT**. Vedi [LICENCE.md](./LICENCE.md).
