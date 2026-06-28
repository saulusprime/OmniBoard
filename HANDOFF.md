# HANDOFF — Storico delle sessioni di lavoro

> Registro cronologico di tutte le sessioni e delle operazioni compiute.
> **La voce più recente è in cima.** Ogni voce descrive contesto, decisioni e modifiche.

---

## 2026-06-28 — Scaffold iniziale: backend, frontend, anagrafica, gruppi, punteggi, classifiche

**Obiettivo della sessione:** primo scaffold funzionante. Interfaccia web di presentazione
con menu, creazione utenti, fondazione gruppi tramite voto, punteggi per gioco e classifiche.

**Realizzato:**
- **Backend FastAPI** (`backend/app/`): modelli SQLAlchemy (User, Game, Score,
  GroupProposal, GroupProposalVote, Group, GroupMembership), schemi Pydantic, router
  `users` / `games` / `groups` / `matches` / `rankings`, hashing password pbkdf2 (stdlib),
  seed del catalogo giochi, creazione tabelle allo startup (SQLite in sviluppo).
- **Frontend Django** (`frontend/`): progetto `scacchi_web` + app `web`. Volutamente
  **senza database** (app DB-dipendenti disattivate, messaggi su cookie); tutte le
  operazioni passano dal backend via `web/api_client.py` (httpx). Pagine: home/presentazione,
  giocatori (lista + creazione), gruppi (proposte + voto), classifiche (universale + per
  gioco con ambito globale/nazionale/regionale), registrazione partita. UI con menu e stile.
- **Engine** (`engine/core.py`): scheletro dell'interfaccia astratta `Game` con hook per
  nodi del caso (non ancora implementati).
- **Funzionalità anagrafica/gruppi/punteggi:** utente con nome, cognome, alias, email,
  nazionalità, regione; fondazione gruppo quando i voti a favore raggiungono la soglia
  (default 2, proponente vota in automatico); punteggio per gioco accumulato registrando
  partite (vittoria +3, patta +1); classifica universale = somma dei punti; classifiche per
  gioco filtrabili per nazione/regione.
- **Tooling:** `Makefile` (install/backend/frontend), `requirements.txt` per backend e
  frontend, README di `backend/` e `frontend/`.

**Decisioni e scelte tecniche:**
- Frontend Django senza DB proprio (coerente con l'architettura: il backend è l'unica fonte
  di verità). Backend e frontend su porte 8000 / 8001.
- Schema punti provvisorio (3/1/0); in futuro rating tipo Elo. Tabella `moves` non ancora
  introdotta (arriverà col motore e la gestione partite end-to-end).
- Per ora niente Alembic: tabelle create con `create_all` (migrazioni in seguito).

**Verifiche eseguite (tutte superate):** installazione dipendenze (Python 3.12, Django 6.0,
FastAPI 0.138); `manage.py check` senza problemi; import dell'app backend; flusso API
completo via curl (creazione utenti, alias duplicato → 409, registrazione partite,
dettaglio punteggi, classifica universale e per gioco globale/nazionale/regionale, proposta
gruppo + voto → fondazione); rendering di tutte le pagine del frontend con dati dal backend;
creazione utente via form Django (CSRF) end-to-end fino alla conferma nel backend.

**Bug trovato e corretto:** i `default` delle colonne SQLAlchemy si applicano al flush, non
all'istanziazione: una `Score` nuova aveva attributi `None` e il `+= 1` falliva. Risolto
inizializzando esplicitamente i valori a 0 alla creazione (`backend/app/routers/matches.py`).

**Prossimi passi:** primo gioco giocabile (Tris) nel motore; autenticazione; regole di
gestione dei gruppi; rendering interattivo della scacchiera.

---

## 2026-06-28 — Avvio della base documentale (stack Django + FastAPI)

**Obiettivo della sessione:** creare la base documentale del progetto e la configurazione
GitHub. Nessun codice applicativo: solo documenti e configurazione del repository.

**Contesto / cambio di rotta:**
- La cartella di progetto era di fatto vuota (repository git inizializzato su `main`, nessun
  commit, presente solo `.claude/settings.json`).
- Rispetto alla sessione del 2026-06-27 è stato deciso un **nuovo stack tecnologico**:
  da TypeScript/React/Node-Express/Prisma si passa a **Python** con **frontend Django**,
  **backend/API FastAPI** e database relazionale. Il precedente codice (monorepo Node/React)
  non è presente in cartella: si riparte da zero con la nuova architettura.

**Decisioni prese:**
- **Licenza:** MIT.
- **Motore:** deterministico ma **estendibile a nodi del caso** (dadi), in coerenza con la
  scelta della sessione precedente di includere in prospettiva backgammon/ludo.
- **Architettura a servizi:** Django = presentazione; FastAPI = API/logica + dati;
  `engine/` = pacchetto Python puro con il modello di gioco astratto; database come unica
  fonte di verità lato backend (PostgreSQL in prod, SQLite in sviluppo).
- **Lingua della documentazione:** italiano.

**Operazioni compiute:**
- Creati i documenti di progetto nella root:
  - `README.md` — documento di progetto (visione, caratteristiche, architettura, stack,
    struttura, roadmap, stato).
  - `HANDOFF.md` — questo storico delle sessioni.
  - `MEMORY.md` — diario tecnico e decisioni architetturali (ADR).
  - `MANUAL.md` — manuale dei giochi (scacchi, dama, tris, forza 4) e dell'applicazione.
  - `LICENCE.md` — licenza MIT + nota sul trattamento dei dati.
- Creati i file di comunità open source:
  - `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`.
- Creata la configurazione GitHub in `.github/`:
  - `workflows/ci.yml` — pipeline di integrazione continua (lint + test, tollerante alla
    fase doc-only).
  - `ISSUE_TEMPLATE/` — moduli per bug report e feature request + `config.yml`.
  - `PULL_REQUEST_TEMPLATE.md`.
  - `dependabot.yml` — aggiornamento automatico delle dipendenze.
- Creati i file di configurazione del repository: `.gitignore`, `.editorconfig`, `.env.example`.

**Stato a fine sessione:** 🟠 base documentale completa; sviluppo del codice non ancora iniziato.

**Prossimi passi suggeriti:**
1. Scaffold del motore astratto `engine/` con le interfacce di base e relativi test.
2. Primo gioco completo (**Tris**) per validare le primitive del motore.
3. Scaffold del backend FastAPI con schema del database e migrazioni.
4. Scaffold del frontend Django con il rendering della scacchiera.

---

## 2026-06-27 — Sessione precedente (storico, stack abbandonato)

> Registrata per continuità storica. **Stack non più in uso.**

Era stato avviato un monorepo full-stack in TypeScript: `server/` (Node + Express + Prisma +
SQLite) e `client/` (Vite + React), con anagrafica giocatori, menu e **Dama italiana**
completa basata su un motore astratto. Erano stati fissati i principi di base: due giocatori,
ammissione di nodi del caso (dadi), piattaforma web. Set di partenza previsto:
Tris, Forza 4, Dama italiana, Backgammon, poi Scacchi.

**Esito:** approccio rivisto. Dal 2026-06-28 il progetto adotta lo stack Python
(Django + FastAPI + database) descritto nella voce sopra. I principi di gioco (2 giocatori,
estendibilità ai nodi del caso, set di giochi) restano validi; cambia l'implementazione.
