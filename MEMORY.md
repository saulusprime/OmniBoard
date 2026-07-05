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

### ADR-010 — Parametri centralizzati + super admin — 2026-06-28
**Contesto:** rendere l'intero programma parametrizzabile e gestibile da un'unica interfaccia.
**Decisione:** un **registro** dei parametri (`settings_service.SETTINGS_DEFS`: tipo, default,
categoria, label) con valori persistiti in tabella `settings`; `get()` legge dal DB con
fallback al default. Le modifiche passano da `PUT /admin/settings` protetto da
`ADMIN_TOKEN` (header `X-Admin-Token`); la lettura è aperta e `GET /config` espone il
sottoinsieme utile al frontend. Il delay/animazione IA resta lato client ma il valore è un
parametro (`ai.move_delay_ms`).
**Conseguenze:** comportamento configurabile a runtime senza ridistribuire; aggiungere un
parametro è una sola voce nel registro. Auth dei *giocatori* ancora assente: per ora il super
admin è protetto da un token condiviso (non da ruoli utente). Nuova tabella `settings` creata
da `create_all` (è additiva: nessun problema di migrazione su DB esistenti).

### ADR-011 — Forza 4 + scacchiera generica + IA a profondità limitata — 2026-06-28
**Contesto:** integrare Forza 4 riusando l'infrastruttura, senza duplicare frontend/AI.
**Decisione:** il motore espone `rows`/`cols`/`move_type` (cell|column) così il frontend rende
una **scacchiera generica** (JS) valida per più giochi; la mossa è un indice generico (cella o
colonna). L'IA locale usa minimax **completo** se `search_depth is None` (Tris) e **limitato +
euristica** se impostato (Forza 4: `search_depth=4`), perché lo spazio di Forza 4 è troppo
grande per la ricerca completa. `/games` espone `playable` (presenza nel registro del motore).
**Conseguenze:** aggiungere un gioco da tavoliere = implementare il `Game` (con geometria e,
se grande, euristica) e registrarlo; il frontend lo gioca senza modifiche. L'IA limitata non è
imbattibile a Forza 4 (compromesso voluto velocità/forza; la profondità è regolabile).

### ADR-012 — Dama italiana + mosse identificate da stringa — 2026-06-28
**Contesto:** la dama ha mosse "da casella a casella" con catture multiple: non più un singolo
indice come Tris/Forza 4.
**Decisione:** una mossa è identificata da una **stringa** (`Game.move_id`): cella (`"4"`),
colonna (`"3"`) o percorso (`"35-21"`). Il backend valida confrontando l'id; `MoveIn.move:str`.
La vista sessione espone `view_board` (simboli per gioco) e `playable_moves` (from/to/captures/
symbol) per i giochi a selezione. Il frontend ha un terzo `move_type` "draughts" (origine→
destinazione). Regole dama: catture obbligatorie a massimo numero, dama corto raggio, pedina
non cattura dama, promozione che termina la mossa. IA: minimax a profondità limitata + euristica.
**Conseguenze:** sistema di mosse generico per qualsiasi gioco futuro (anche gli scacchi).
Restano da implementare le priorità FID fini e le patte (semplificazioni documentate).

### ADR-013 — Scacchi completi + libro di aperture + alpha-beta — 2026-06-28
**Contesto:** integrare gli scacchi (gioco di riferimento) e "gestire le tecniche di apertura".
**Decisione:** motore scacchi completo (mosse legali con filtro di scacco, arrocco, en passant,
promozione, matto/stallo, 50 mosse, materiale insufficiente), validato con **perft**. Un
**libro di aperture** in UCI (`openings.py`) riconosce l'apertura (`detect_opening`) e fornisce
continuazioni (`book_move`); l'IA gioca il libro in apertura, poi minimax. Aggiunta la potatura
**alpha-beta** (richiesta dalla profondità degli scacchi; rimossa la memoization per mantenere
i valori esatti con alpha-beta). `choose_move(game, state, history)` riceve lo storico (id UCI);
la vista sessione espone il nome dell'apertura; il log registra l'id mossa.
**Conseguenze:** l'IA segue Italiana/Siciliana/Scozzese/… in apertura. Semplificazione: niente
patta per ripetizione (richiede lo storico nello stato). Profondità IA 3 (compromesso velocità).

### ADR-014 — IA remota robusta + risincronizzazione client — 2026-06-28
**Contesto:** errore "bad request" su `mossa.json` dopo alcuni minuti (desync client/server).
**Decisione:** `_qwen_move` ora individua la mossa per **id** (`_match_move`, valido per ogni
gioco) anziché per intero — prima non combaciava mai per scacchi/dama, sprecando una chiamata
HTTP a ogni mossa IA; timeout configurabile (`QWEN_TIMEOUT`). Il frontend, in caso di errore,
**si risincronizza** con lo stato reale (`GET …/stato.json`) invece di fare revert.
**Conseguenze:** niente disallineamenti persistenti; l'IA remota funziona per tutti i giochi.

### ADR-015 — Login provider IA: token in DB configurabili da super admin — 2026-06-28
**Contesto:** richiesta di non modificare a mano il `.env` per la chiave Qwen, ma offrire
un'interfaccia di login verso uno o più servizi IA (Qwen, Claude, …) che autoconfigura il token.
**Decisione:** introdotti i **provider IA** come entità di dominio (tabella `ai_providers`:
codice, etichetta, `kind`, base_url, modello, **token**) con un registro dei provider noti
(`ai_providers.py`) e un parametro `ai.provider` per il provider **attivo**. L'IA (`ai.py`) è
multi-provider: dispatch per `kind` → `openai` (httpx, per Qwen/OpenAI) o `anthropic` (**SDK
ufficiale**, per Claude: niente `temperature` sui modelli 4.x, gestione `stop_reason="refusal"`).
Configurazione via `GET/PUT /admin/ai-providers` + `POST …/{code}/test` e pagina `/admin/ia/`.
Al primo avvio `seed_providers` **migra** un eventuale `QWEN_API_KEY` da ambiente.
**Sicurezza:** il token **non è mai restituito** dall'API (solo `has_key`); la scrittura richiede
`X-Admin-Token`; un campo token vuoto conserva quello esistente. **Compromesso:** in sviluppo il
token è salvato **in chiaro** nel DB — in produzione va cifrato / spostato in un secret manager.
**Alternativa scartata:** continuare con le sole variabili d'ambiente (non autoconfigurabili da
UI, una sola IA per volta).

### ADR-016 — Chiamata IA remota: niente auto-attivazione + connect timeout breve — 2026-06-28
**Contesto:** dopo aver preregistrato Qwen via `.env` e averlo **auto-attivato**, il backend si
è **bloccato**: il provider remoto veniva chiamato **in linea** nella richiesta di mossa e il
connect verso l'endpoint Qwen su IPv6 irraggiungibile restava in `SYN_SENT`; le chiamate si
accumulavano e l'API smetteva di rispondere. (Qwen è inoltre a quota esaurita → 403.)
**Decisione:**
- `seed_providers` **non attiva** automaticamente alcun provider: la preregistrazione memorizza
  solo il token; l'attivazione è esplicita dal super admin. Attivare un provider non verificato
  scatena chiamate remote inutili a ogni mossa.
- le chiamate remote usano un **connect timeout breve** (`httpx.Timeout(total, connect=min(4,
  total))`, sia OpenAI-compatible sia Anthropic): un endpoint irraggiungibile fallisce in fretta
  e si ripiega sul **giocatore locale**.
**Conseguenze:** l'IA è sempre reattiva (in assenza di provider valido gioca in locale); un
provider remoto si attiva consapevolmente dopo averlo verificato con «Verifica connessione».
**Possibile evoluzione:** spostare la mossa IA fuori dal ciclo di richiesta (task/async) e/o un
*circuit breaker* che disattiva temporaneamente un provider che fallisce ripetutamente.

### ADR-017 — IA scacchi: motore dedicato + modello dell'avversario — 2026-06-28
**Contesto:** richiesta di potenziare al massimo l'IA degli scacchi: analizzare la scacchiera
mossa dopo mossa, confrontarsi con gli schemi principali, e studiare lo storico dell'avversario
per individuarne schemi e debolezze.
**Decisione:**
- **Motore dedicato** (`engine/games/chess_engine.py`) invece dell'LLM remoto (più debole a
  scacchi): negamax alpha-beta con iterative deepening (budget di tempo), transposition table,
  quiescence search, ordinamento mosse (TT/MVV-LVA/killer/history), valutazione ricca
  (materiale + PST per fase + struttura pedonale + sicurezza re + coppia alfieri + torri su
  colonna aperta). Ordine in `choose_move`: libro → motore → provider → locale.
- **Modello avversario** (`backend/app/chess_profile.py`): dallo storico delle partite concluse
  ricava aperture/rendimento, fragilità tattica (sconfitte rapide), tendenza alla patta, finali;
  ne deriva **debolezze** e **stile** (`aggression`, `contempt`) passato al motore quando l'IA
  affronta quell'umano. Profilo esposto via `GET /users/{id}/chess-profile` e in UI.
**Conseguenze:** IA scacchi forte e adattiva; budget tempo configurabile (`ai.engine_ms`, tetto
`AI_ENGINE_MS_MAX`); jitter alla radice per varietà tra partite senza perdita di forza.
**Alternativa scartata:** affidare la forza scacchistica all'LLM remoto (debole, lento, costoso).
**Possibile evoluzione:** scelta dell'apertura-bersaglio e stima delle blunder via rianalisi.

### ADR-018 — Mosse IA in background (thread per sessione + polling) — 2026-06-28
**Contesto:** la mossa IA era calcolata dentro la richiesta HTTP: 2s bloccanti per mossa col
motore scacchi, minuti per una sessione IA-vs-IA (già mitigato con un tetto, ma il difetto
strutturale restava — vedi ADR-016).
**Decisione:** la logica di svolgimento partite vive in `gameplay.py`; `schedule_ai` lancia al
massimo **un thread per sessione** (set + lock, idempotente) con sessione DB propria; commit
**per mossa** così il client vede i progressi. Endpoint di creazione/mossa rispondono subito;
`GET /sessions/{id}` fa **auto-ripristino** (riprogramma l'IA se nessun worker è attivo, mai
calcolo inline nei GET). Client in **polling** con spinner e animazione. Configurabile:
`ai.async_moves` (super admin) + env `AI_ASYNC` (test → `0`, sincrono).
**Alternative scartate:** BackgroundTasks di FastAPI (legato al ciclo di richiesta, scomodo per
auto-ripristino e idempotenza); coda esterna (Celery/Redis: giusta per multi-processo, eccessiva
per lo scaffold — annotata in TODO.md); WebSocket (arriverà col tempo reale).
**Conseguenze:** nessuna risposta bloccante; le partite IA-vs-IA si guardano in diretta; il
limite è lo scheduling in-process (un solo worker uvicorn).

### ADR-019 — Struttura del motore: una directory per gioco, common/, una classe per file — 2026-07-05
**Contesto:** i giochi erano moduli singoli in `engine/games/` (regole, stato, helper e — per
gli scacchi — anche il motore di ricerca nello stesso file o in file affiancati): file lunghi,
difficile orientarsi.
**Decisione:** ogni gioco ha una **directory dedicata** (`engine/tictactoe/`, `connect4/`,
`draughts/`, `chess/`); le parti condivise stanno in **`engine/common/`** (`game.py`,
`outcome.py`, `registry.py`); **una classe per file** (regole in `game.py`, stato in
`state.py`; per gli scacchi anche `board.py` per le funzioni di scacchiera condivise,
`engine.py` per la ricerca, `context.py` per `SearchContext`, `errors.py` per `TimeUp`,
`openings.py` per il libro). Il pacchetto `engine` ri-esporta l'**API stabile**
(`Game`, `Outcome`, `get_game`, `is_playable`, …): i consumatori importano da `engine` o da
`engine.<gioco>`, mai dai moduli interni. Spostamenti fatti con `git mv` (storia preservata).
**Conseguenze:** aggiungere un gioco = nuova directory + registrazione in `common/registry.py`;
i moduli restano corti e a responsabilità unica. Eccezione consapevole: le classi private di
supporto alla ricerca sono comunque in file dedicati (`context.py`, `errors.py`).
**Alternativa scartata:** mantenere `games/` piatto con moduli monolitici (non scala con
motori dedicati, libri di aperture e futuri giochi stocastici).

### ADR-020 — Tre tipi di avversario, un modulo per tipo (opponents/) — 2026-07-05
**Contesto:** l'avversario deve poter essere umano, **Stockfish (NNUE)** configurabile o
**IA via API** (Qwen/Claude/…); il vecchio `ai.py` mescolava chiamate remote e giocatore
locale in un unico modulo.
**Decisione:** pacchetto `backend/app/opponents/` con un modulo per responsabilità:
`api_ai.py` (solo chiamate ai provider remoti + ping), `stockfish.py` (ponte **UCI
one-shot** in subprocess: senza stato, thread-safe coi worker; posizione via
`startpos+moves` o FEN con il nuovo `Chess.to_fen`; forza via Skill Level / UCI_Elo /
movetime dal super admin), `local.py` (ripiego sempre disponibile: motore dedicato scacchi
o minimax generico), `__init__.py` (dispatcher per tipo, libro aperture comune, sorgente
della mossa tracciata). Tipo per lato persistito in `game_sessions.x/o_ai_kind`
("ai"|"stockfish", None=umano; righe storiche ⇒ "ai").
**Cambio voluto:** con tipo "ai" il provider remoto **gioca davvero** anche a scacchi
(prima il motore interno lo scavalcava); il motore interno resta il ripiego di tutti.
**Conseguenze:** codice per-avversario leggibile e testabile in isolamento (ponte UCI
provato con un finto binario); la partita non si blocca mai (ripiego garantito).
⚠️ Schema DB cambiato senza migrazioni: in sviluppo ricreare `backend/scacchi.db`.
**Alternativa scartata:** processo Stockfish persistente con lock (più veloce di ~100ms a
mossa ma con stato condiviso tra thread; annotato in TODO.md come ottimizzazione).

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
- **2026-06-28** — **Parametri di programma centralizzati** + interfaccia **super admin**
  (token): punteggi, voti gruppo, registrazione utenti, ritardo IA, max batch configurabili a
  runtime. 33 test verdi.
- **2026-06-28** — Secondo gioco: **Forza 4** (motore + euristica), scacchiera **generica** nel
  frontend (clic-cella o caduta-colonna), IA a profondità limitata per i giochi grandi. 42 test verdi.
- **2026-06-28** — Terzo gioco: **Dama italiana** (catture obbligatorie/massimo, dame, promozione);
  codifica mossa generica per id (cella/colonna/percorso), scacchiera con selezione origine→
  destinazione. 50 test verdi.
- **2026-06-28** — Quarto gioco: **Scacchi** completi (verificati con perft) + **libro di
  aperture** (riconoscimento + IA che segue le linee) + potatura alpha-beta. 58 test verdi.
- **2026-06-28** — **Login provider IA** multi-provider (Qwen/Claude/OpenAI): token configurabili
  da super admin e salvati in DB (mai esposti dall'API), provider attivo selezionabile, pagina
  `/admin/ia/` con verifica connessione. 66 test verdi.
- **2026-06-28** — `.env` legge anche dal backend + preregistrazione Qwen; poi **fix freeze**:
  niente auto-attivazione di provider non verificati e **connect timeout** breve sulle chiamate
  IA remote (un endpoint irraggiungibile non blocca più il backend). 68 test verdi.
- **2026-06-28** — **IA scacchi potenziata**: motore alpha-beta dedicato (iterative deepening,
  quiescence, transposition table, valutazione ricca) + **modello dell'avversario** dallo storico
  (schemi, debolezze → stile aggression/contempt). 79 test verdi.
- **2026-06-28** — **Fix qualità motore scacchi**: la ricerca arrivava solo a profondità 2–3
  (da cui il gioco "suicida"). Ricerca pseudo-legale, quiescence su sole catture + delta pruning,
  eval a tabelle precalcolate, NamedTuple, null-move, estensione di scacco, LMR, anti-ripetizione,
  jitter fuori dalla ricerca → profondità 4–6, matto al vecchio minimax in 67 semimosse.
- **2026-06-28** — **Mosse IA in background** (`gameplay.py`: un thread per sessione, idempotente,
  auto-ripristino dai GET) + polling con animazione nel client; parametro `ai.async_moves`;
  creato **TODO.md** (backlog delle idee). POST mossa: da ~2s bloccanti a 0.017s. 82 test verdi.
- **2026-06-28** — **Libro di aperture ampliato**: 75+ linee con varianti (validate dai test
  rigiocandole col motore), indicizzato **per posizione** (gioca da libro anche nelle
  trasposizioni), estendibile via `CHESS_BOOK_FILE`; nomi da generico a specifico
  (*Siciliana* → *Siciliana Najdorf*). 87 test verdi.
- **2026-07-05** — **Refactor del motore** (ADR-019): una directory per gioco, parti comuni in
  `engine/common/`, una classe per file (`game.py`/`state.py`; scacchi anche `board.py`,
  `engine.py`, `context.py`, `errors.py`, `openings.py`). API stabile ri-esportata da
  `engine`. 87 test verdi, nessun cambiamento funzionale.
- **2026-07-05** — **Tre tipi di avversario** (ADR-020): umano / **Stockfish UCI** configurabile
  (path, Skill Level, Elo, movetime) / **IA via API**, con pacchetto `opponents/` (un modulo per
  tipo + ripiego locale garantito) e ponte UCI testato con un finto binario. 94 test verdi
  (+1 skip col vero Stockfish). ⚠️ nuove colonne `x/o_ai_kind` → ricreare il DB di sviluppo.
- **2026-07-05** — **Fix forza Stockfish**: il `quit` accodato dopo `go` interrompeva la ricerca
  (bestmove a profondità ~1 → gioco debole); ora il dialogo UCI attende `bestmove` con watchdog.
  **Sei livelli** con divinità greche: Zeus (Extreme, piena forza/4s) → Atena 2700 → Apollo 2350
  → Ares 2000 → Hermes 1700 → Pan (Learner, 1400/0.5s), selezionabili al setup per lato.
  101 test verdi. ⚠️ nuove colonne `x/o_ai_level` → ricreare il DB di sviluppo.
- **2026-07-05** — **Animazione delle mosse + suono**: i pezzi scivolano (flyer assoluti con
  transizione CSS; accoppiamento origine→destinazione per simbolo: copre arrocco/en passant/
  promozione; Forza 4 con caduta, Tris con pop) e ogni mossa ha un "toc" WebAudio sintetizzato
  (più grave sulle catture). Personalizzabili dal super admin (categoria «Aspetto»: `ui.anim_ms`,
  `ui.sound_enabled`, `ui.sound_volume`) via `GET /config`. 101 test verdi.
- **2026-07-05** — **Orologio di gioco scacchi**: categorie Blitz (<15′), Rapid (15–60′),
  Classical (>60′) con incremento Fischer opzionale, e FIDE ufficiale fisso (90′+30″/mossa,
  +30′ alla 40ª). Server = arbitro (`consume_time`/`check_time` pigra, `_now` monkeypatch-abile);
  patta col re nudo alla bandierina; l'IA sotto orologio limita la pensata a ~1/10 del residuo.
  Due orologi live in pagina. 106 test verdi. ⚠️ nuove colonne orologio → ricreare il DB.
- **2026-07-05** — **Ritmo di visione** (`ai.watch_pace_ms`, default 1200 ms; env
  `AI_WATCH_PACE_MS`): pausa minima nel worker tra le mosse IA-vs-IA e prima della prima mossa
  quando apre l'IA → la scacchiera è disegnata prima della prima mossa e ogni mossa arriva
  singola, animata. Con l'orologio la pausa è "dell'arbitro" (non consuma tempo). 107 test verdi.

## Questioni aperte

- Strategia di autenticazione tra Django e FastAPI (sessione vs token): da definire allo
  scaffold del backend.
- Scelta tra Django template + Canvas e un approccio più ricco lato client per la scacchiera.
- Formato di notazione delle mosse da persistere (specifico per gioco vs generico).
- ORM lato backend (SQLAlchemy) e gestione migrazioni con Alembic: da confermare.
