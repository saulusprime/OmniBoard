# OmniBoard — Piattaforma universale per giochi da tavolo a turni

> Gioca a **scacchi** e a tutti gli altri giochi da tavolo a **turni e a informazione perfetta**
> (dama, tris, forza 4, …) tramite un unico motore astratto, direttamente dal browser.

[![CI](https://github.com/saulusprime/OmniBoard/actions/workflows/ci.yml/badge.svg)](https://github.com/saulusprime/OmniBoard/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENCE.md)
[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/stato-in%20sviluppo%20attivo-brightgreen.svg)](#stato-del-progetto)

> **Ultimo aggiornamento:** 2026-07-11 — *Sette giochi giocabili (con Othello e Gomoku); scacchi FIDE-completi con analisi/coach/puzzle; motori dedicati per scacchi, dama, Forza 4 e Gomoku; navigazione ad aree sul modello chess.com con home-cruscotto; rating Elo con stagioni; Arena IA con tornei; interfaccia bilingue IT/EN e accessibile; 323 test.*

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

**OmniBoard** è una piattaforma web open source per giocare in **due** a giochi da tavolo a
turni. L'idea portante è un **motore di gioco astratto** che modella in modo generico stato,
mosse legali e condizioni di vittoria: ogni gioco concreto (scacchi, dama, ecc.) è un
*plugin* che implementa questo modello. Aggiungere un nuovo gioco significa scrivere le sue
regole, non riscrivere l'infrastruttura.

Il progetto nasce attorno agli **scacchi** come gioco di riferimento, ma è progettato fin
dall'inizio per ospitare l'intera famiglia dei giochi a **informazione perfetta** e, in
prospettiva, anche quelli con **nodi del caso** (dadi) come backgammon e ludo.

## Caratteristiche principali

- ♟️ **Motore astratto unico** condiviso da tutti i giochi (logica pura, testabile, senza I/O);
  nodi del caso inclusi: il **Backgammon** è vivo, i dadi li tira il server.
- 🤖 **Quattro tipi di avversario** per lato: umano (stesso schermo o **a distanza**),
  **motore locale a livelli** (Maestro→Novizio, con errori "umani" calibrati), **Stockfish**
  (processo persistente, preset Zeus→Pan) e **IA via API** multi-provider (Claude, Gemini,
  Grok, Qwen, OpenAI — token **cifrati** nel DB, **circuit breaker** sulle chiamate, ripiego
  locale: la partita non si blocca mai). Mosse IA in una **coda di lavoro** con pool limitato
  e ripresa automatica al riavvio.
- ♟️ **Scacchi FIDE-completi** (arrocco, en passant, promozione con dialog grafico, patta per
  ripetizione/posizione morta, abbandono e patta d'accordo, orologio Blitz/Rapid/Classical/
  FIDE con bandierina art. 6.9) — motore con alpha-beta, quiescence+SEE, PVS, aspiration,
  finali dedicati e **pondering**; **libro aperture** interno/PGN/**Polyglot** con
  apertura-bersaglio dal profilo avversario; **posizione iniziale da FEN** ed **export PGN**.
- 🔬 **Analisi e coaching**: analisi post-partita Stockfish con moviola/note/grafico,
  **badge di qualità** per mossa (💎 sacrifici geniali inclusi), commentatore LLM,
  «**Spiegami questa mossa**», hint per principianti, **anti-tilt** e bias cognitivi misurati.
- 🧩 **Puzzle**: matti autoriali verificati + generazione **dai blunder delle tue partite**,
  progressi per utente, matto alternativo accettato.
- 📈 **Gamification**: **rating Elo** per gioco con **stagioni** (K adattivo FIDE), punti,
  classifiche globali/nazionali/regionali, **Arena IA** (Elo dei concorrenti IA + **tornei**
  round-robin), **statistiche avanzate** (serie, esiti, cadenze, colori, **quattro aspetti
  del gioco**: aperture/tattica/strategia/finali) e raccolta delle
  **mosse geniali** con screenshot.
- 🌐 **Community**: registrazione approvata dal super admin, login a token, presenza online,
  **sfide come inviti** (gioco/colore/cadenza; la partita a distanza nasce all'accettazione),
  **notifiche** con campanella in navbar (sfide, inviti ai gruppi, turni e verdetti dei
  tornei), **gruppi** con fondazione per voto e gestione completa (ruoli
  founder/admin/member, inviti, espulsioni, classifica interna), **tornei fra giocatori**
  a eliminazione diretta (tabellone con seed dall'Elo e bye) o girone all'italiana,
  anche riservati a un gruppo, **sfide gruppo-vs-gruppo** a squadre su più tavolieri
  (formazioni automatiche per Elo, colori alternati, un punto a tavolo), **partite in
  diretta** per spettatori e **replay animato** delle partite concluse.
- 🎓 **Istruzione guidata** («Impara») con lezioni passo-passo e **TTS** multilingua.
- 🖥️ **UI curata**: scacchiera da torneo con coordinate, drag&drop, temi, rotazione,
  pezzi catturati; **responsive mobile**; **accessibile** (tastiera + ARIA); **bilingue
  IT/EN** su tutto lo stack (backend compreso).
- 🛠️ **Tutto parametrizzabile** dall'interfaccia **super admin** (protetta da token).
- 🔓 **Open source** con licenza [MIT](./LICENCE.md).

## Giochi supportati

| Gioco        | Tipo                 | Stato        |
|--------------|----------------------|--------------|
| Tris         | Deterministico       | ✅ Giocabile (umano e IA) |
| Forza 4      | Deterministico       | ✅ Giocabile (umano e IA) |
| Dama italiana| Deterministico       | ✅ Giocabile (umano e IA) |
| Scacchi ♟️    | Deterministico       | ✅ Giocabile (umano e IA, con libro aperture) |
| Backgammon   | Con nodi del caso 🎲  | ✅ Giocabile (umano e IA; il server tira i dadi) |
| Othello      | Deterministico       | ✅ Giocabile (umano e IA; passo automatico) |
| Gomoku       | Deterministico       | ✅ Giocabile (umano e IA; motore dedicato) |

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
│   ├── connect4/        # Forza 4: regole + motore dedicato bitboard (engine.py)
│   ├── backgammon/      # Backgammon: primo gioco stocastico (nodi del caso)
│   ├── othello/         # Othello: regole con passo automatico + euristica posizionale
│   ├── gomoku/          # Gomoku: regole + motore dedicato sui candidati (engine.py)
│   ├── draughts/        # Dama italiana: regole FID + motore dedicato (engine.py)
│   ├── chess/           # Scacchi:
│   │   ├── game.py      #   regole (classe Chess)
│   │   ├── state.py     #   stato immutabile (ChessState)
│   │   ├── board.py     #   scacchiera: costanti e funzioni di base
│   │   ├── engine.py    #   ricerca (alpha-beta, quiescence+SEE, PVS, TT, finali)
│   │   ├── context.py   #   contesto di ricerca (SearchContext)
│   │   ├── errors.py    #   eccezioni del motore (TimeUp)
│   │   ├── openings.py  #   libro delle aperture interno
│   │   ├── pgn.py       #   parser + scrittore SAN/PGN
│   │   └── polyglot.py  #   libri di aperture Polyglot (.bin)
│   └── tests/           # test del motore e dei giochi
│
├── backend/             # servizio FastAPI + accesso al database
│   └── app/
│       ├── main.py      # app FastAPI (migrazioni + seed + router)
│       ├── models.py    # modelli SQLAlchemy (utenti, giochi, punteggi, gruppi)
│       ├── schemas.py   # schemi Pydantic
│       ├── gameplay.py  # svolgimento partite (+ jobqueue.py: coda mosse IA)
│       ├── opponents/   # avversari non umani, un modulo per tipo:
│       │   ├── api_ai.py     #   IA via API (con circuit breaker)
│       │   ├── stockfish.py  #   motore Stockfish via protocollo UCI (persistente)
│       │   └── local.py      #   motore locale a livelli (ripiego sempre disponibile)
│       ├── (un modulo per sistema: analysis, commentary, insights, puzzles,
│       │    rating, ai_arena, human_tournaments, group_matches, notifications,
│       │    tilt, ponder, i18n+catalog_en, token_crypto, …)
│       ├── migrations/  # Alembic (0001…0013)
│       └── routers/     # users, auth, games, groups, group_matches, sessions,
│                        #   rankings, arena, tournaments, challenges,
│                        #   notifications, puzzles, admin, community, lessons, tts
│
└── frontend/            # progetto Django (presentazione, nessun DB proprio)
    ├── omniboard_web/     # settings, urls, wsgi/asgi
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

## Avvio rapido

Servono Python 3.12+. Il repository usa un **submodule git**
(`integrazioni/KittenTTS`: sintesi vocale locale per la futura istruzione guidata):
clona con `git clone --recursive …` oppure esegui `git submodule update --init`
dopo il clone (`make install` lo fa da solo). I due servizi (backend e frontend)
si avviano in due terminali. Con il `Makefile` di comodo:

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

Apri <http://127.0.0.1:8001/>. All'avvio il backend applica da solo le **migrazioni
Alembic** (`backend/migrations/`) portando lo schema SQLite (`backend/omniboard.db`)
all'ultima revisione, e popola il catalogo dei giochi. Un cambio di schema non richiede
più di ricreare il database: `make migration m="descrizione"` genera la revisione dai
modelli e il riavvio la applica (oppure `make migrate`). Il frontend non usa database.
Configurazione tramite `.env` (vedi `.env.example`).

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
- [x] **Tre tipi di avversario** (umano / Stockfish UCI configurabile / IA via API) con codice separato per tipo (`opponents/`)
- [x] Autenticazione/login dei giocatori (registrazione approvata dal super admin, sessioni a token)
- [x] Regole di gestione dei gruppi (ruoli founder/admin/member, inviti con accettazione, espulsioni, classifica interna) + tornei fra giocatori e sfide gruppo-vs-gruppo
- [x] Migrazioni del database (Alembic); PostgreSQL in produzione resta da provare
- [x] Gioco a distanza fra client diversi (polling strutturato; mosse autorizzate col token del giocatore) + area Community con presenza online e badge punti
- [x] Affinamento regole dama (cascata di priorità FID completa fra catture, ripetizione) + motore dedicato
- [x] Scacchi: patta per ripetizione e posizione morta (audit FIDE nel MANUAL), libro esteso (testo/PGN/Polyglot), apertura-bersaglio, analisi post-partita, sparring Elo, hint, badge di qualità + commentatore LLM
- [x] Sistema di rating **Elo** per gioco e stagione (K adattivo FIDE), accanto ai punti attività
- [x] **Backgammon**: primo gioco stocastico — nodi del caso realizzati (il server tira i dadi)
- [x] **Forza 4**: motore dedicato bitboard (negamax + TT + approfondimento iterativo, tattica esatta a ogni nodo)
- [x] Sesto e settimo gioco giocabili: **Othello** (giri e passo automatico, tavoliere verde) e **Gomoku** (goban 15×15, motore dedicato sui candidati vicini)
- [x] **Riorganizzazione del frontend ad aree** sul modello chess.com (navbar a 5 aree con menu a discesa, hub Gioca e Guarda, Community ristretta con pagina Notifiche, home-cruscotto per il loggato)

## Stato del progetto

🟢 **Sette giochi giocabili, piattaforma completa in sviluppo attivo.** Backend FastAPI e
frontend Django girano end-to-end: autenticazione con approvazione del super admin, partite
in locale e **a distanza** (sfide come inviti, notifiche, spettatori e replay animato),
sette giochi (Tris, Forza 4, Dama italiana, Scacchi, Backgammon, Othello, Gomoku),
quattro tipi di
avversario con ripiego locale, analisi e coaching per gli scacchi, puzzle, rating Elo con
stagioni, Arena IA, tornei fra giocatori e sfide di gruppo a squadre, statistiche avanzate
(quattro aspetti, sottocategorie tattiche, confronto coi pari fascia), **navigazione ad
aree** sul modello chess.com (Gioca/Puzzle/Impara/Guarda/Community, home-cruscotto),
interfaccia **bilingue IT/EN**, **accessibile** e **responsive**. Suite di **323 test**
(motore + backend + frontend) eseguita a ogni passo e in **CI** su GitHub Actions; schema
DB governato da migrazioni Alembic (0001…0013). Il backlog vivo è in [TODO.md](./TODO.md);
le voci realizzate in [ASIS.md](./ASIS.md); lo storico dei lavori in [HANDOFF.md](./HANDOFF.md).

## Documentazione correlata

- [HANDOFF.md](./HANDOFF.md) — storico delle sessioni di lavoro.
- [MEMORY.md](./MEMORY.md) — diario tecnico e decisioni architetturali.
- [MANUAL.md](./MANUAL.md) — manuale dei giochi e dell'applicazione.
- [TODO.md](./TODO.md) — backlog delle idee di potenziamento e miglioramento.
- [ASIS.md](./ASIS.md) — voci di backlog realizzate (spostate da TODO.md).
- [CONTRIBUTING.md](./CONTRIBUTING.md) — come contribuire.
- [LICENCE.md](./LICENCE.md) — licenza e nota sul trattamento dei dati.

## Come contribuire

I contributi sono benvenuti! Leggi [CONTRIBUTING.md](./CONTRIBUTING.md) e il
[Codice di Condotta](./CODE_OF_CONDUCT.md). Per segnalare una vulnerabilità di sicurezza
consulta [SECURITY.md](./SECURITY.md).

## Licenza

Distribuito con licenza **MIT**. Vedi [LICENCE.md](./LICENCE.md).
