# MEMORY — Diario tecnico e decisioni architetturali

> Diario tecnico del progetto **OmniBoard** (già «Scacchi»): andamento, traguardi, dettagli architetturali e
> scelte tecniche con le relative motivazioni. Complementare a [HANDOFF.md](./HANDOFF.md)
> (che è il registro cronologico delle sessioni). Le decisioni rilevanti sono annotate come
> *ADR* (Architecture Decision Record).
>
> **Ultimo aggiornamento:** 2026-07-07

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

### ADR-021 — Nodi del caso: il server tira i dadi (Backgammon) — 2026-07-05
**Contesto:** il Backgammon è il primo gioco stocastico; gli hook `is_chance_node`/
`chance_outcomes` esistevano dal giorno uno ma mancava chi applicasse gli eventi.
**Decisione:** il contratto `Game` si completa con **`apply_chance`** (+ `describe_chance`
e `view_status`); l'estrazione casuale è responsabilità del **backend** — `gameplay.
resolve_chance` tira i dadi (estrazione pesata), registra il tiro nel log («🎲 5-3») e
gestisce i turni che passano da soli quando il tiro è ingiocabile. Chiamata pigra dalle
letture di stato e prima/dopo le mosse: chiunque "tocchi" la partita materializza il tiro.
Il **motore resta deterministico e testabile** (i test applicano tiri espliciti).
Modello del turno: **un dado = una mossa** (stato con dadi residui; doppio = 4 mosse;
`_normalize` chiude il turno) — l'alternativa "una mossa = l'intero turno" esplode
combinatoriamente e non si sposa con la UI a selezione.
**Conseguenze:** vale per ogni futuro gioco coi dadi (Ludo); l'IA locale gioca greedy
dado per dado (`search_depth=1`) — expectiminimax in TODO. Nessun cambio schema DB.
**Semplificazioni documentate:** niente tiro iniziale "un dado a testa", regola del dado
maggiore, cubo del raddoppio, gammon/backgammon.

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
- **2026-07-05** — **Ritmo di visione** (`ai.watch_pace_ms`, default 1000 ms; env
  `AI_WATCH_PACE_MS`): ritardo minimo nel worker per **ogni** mossa dell'IA — risposta
  all'umano inclusa (niente mosse "incollate"), IA-vs-IA una mossa alla volta, prima mossa
  dopo che la scacchiera è disegnata. Con l'orologio la pausa è "dell'arbitro" (non consuma
  tempo). 108 test verdi.
- **2026-07-05** — **Animazioni per intero** (`play.html`): percorsi a tappe con `flyPiece`
  (`ui.anim_ms` per segmento) — cavallo a "L", prese multiple della dama salto per salto
  (catena ricostruita dal diff, vittime che spariscono quando scavalcate), promozioni con
  pezzo originale in volo e trasformazione all'arrivo, catturati visibili fino
  all'atterraggio. Sintassi JS validata con `node --check`. 108 test verdi.
- **2026-07-05** — **Backgammon giocabile** (ADR-021): quinto gioco, primo stocastico — i nodi
  del caso funzionano (il **server tira i dadi**, `resolve_chance`, tiri nel log «🎲 5-3»);
  un dado = una mossa, colpi/barra/uscita, vista 2×14 sul frontend generico, IA greedy.
  121 test verdi. `integrazioni/` (codice esterno utente) esclusa dal lint, non committata.
- **2026-07-05** — **KittenTTS submodule + dipendenza**: `integrazioni/KittenTTS` registrato
  come submodule git (pinnato a v0.8.1, `9f3e0d8`) e aggiunto a `backend/requirements.txt`
  come path dep (`./integrazioni/KittenTTS`, installazione dalla root); `make install` fa
  `git submodule update --init`. Servirà per il TTS della sezione di istruzione guidata
  (piano in TODO.md; limite lingua: solo inglese — per l'italiano valutare Piper).
- **2026-07-05** — **Opzioni giocatore (estetica)**: `User.prefs_json` + registro
  `user_prefs.py` + `PUT /users/{id}/prefs` (personale, senza token); temi scacchiera/pezzi
  (classico/legno/smeraldo/ghiaccio, valgono per scacchi e dama), segno del Tris a scelta
  (✕ ✖ ★ ☆ ♥ ◆ ▲, collisione risolta lato server), **tavolo del Backgammon classico e non
  tematizzabile** (punte SVG, legno, barra/vasche). Form nella scheda giocatore. 124 test
  verdi. ⚠️ nuova colonna `users.prefs_json` → ricreare `backend/scacchi.db`.
- **2026-07-05** — **Pezzi a tinta piena + WCAG 2.1**: `displayOf` mostra sempre i glifi
  pieni (♔→♚, ⛀→⛂, ○→●; il lato lo colora il CSS), lato chiaro bordato di scuro con
  `-webkit-text-stroke`+`paint-order`; 26 coppie pezzo/casa verificate ≥3:1 (SC 1.4.11),
  minimo 4.47:1. Riferimento: `temi/scacchi-posizione-iniziale-pezzi.jpg`.
- **2026-07-05** — **Registrazione con approvazione + autenticazione**: la registrazione è
  una richiesta (`is_approved=False`) che **solo il super admin** accetta/respinge
  (`POST /users/{id}/approve`, `DELETE /users/{id}`, X-Admin-Token); login/logout con
  sessione a token (`auth_sessions`, `/auth/login|me|logout`, durata `users.session_hours`),
  password solo hash PBKDF2 in anagrafica, 401 anti-enumerazione. Frontend: sessione Django
  su cookie firmato (nessun DB), pagine Accedi/Esci, approvazioni in Admin. 129 test verdi.
  ⚠️ nuova colonna `users.is_approved` + tabella `auth_sessions` → ricreare
  `backend/scacchi.db`.
- **2026-07-05** — **Migrazioni Alembic** (fine dell'era create_all): schema in
  `backend/migrations/` (revisione 0001 = baseline, autogenerate), URL da `app.database`
  (mai in alembic.ini), `render_as_batch` per SQLite. `app/db_migrate.py` nel lifespan:
  upgrade automatico all'avvio, **adozione** dei DB create_all a baseline con `stamp`,
  errore chiaro se più vecchi. Test guardiano `compare_metadata` (modelli↔migrazioni).
  Workflow nuovo: modelli → `make migration m="..."` → riavvio. NIENTE più
  `rm backend/scacchi.db`. 132 test verdi.
- **2026-07-05** — **Gioco a distanza + Community**: partite fra client diversi con
  polling strutturato; nelle sessioni `remote` la mossa richiede il **token del giocatore
  al tratto** (401/403 dal server; hotseat invariato); il client comanda solo `MY_SIDE`.
  Presenza online via **heartbeat** (`/auth/heartbeat`, finestra
  `community.online_window_s`), area **Community** (`/community/`: online + «⚔️ Sfida» +
  «Le tue partite», auto-aggiornanti), badge navbar presenza + punti complessivi
  (`UserOut.universal_points`). Migrazione **0002**. 136 test verdi + e2e dal vivo.
- **2026-07-05** — **Concorrenti IA multipli**: catalogo con **Gemini** e **Grok**
  (OpenAI-compatible) oltre a Qwen/Claude/OpenAI; al setup ogni lato sceglie il SUO
  concorrente («IA — Claude», «IA — Gemini», …, voce generica = provider attivo);
  colonne `x/o_ai_provider` (migrazione **0003**), `PlayerSpec.provider` validato,
  `ai_providers.get_config(db, code)`, risoluzione per lato in `advance_ai`
  (Claude-vs-Gemini possibile), etichetta del concorrente in partita. Ripiego locale
  invariato. 140 test verdi. In TODO: classifica delle IA e tornei fra provider.
- **2026-07-06** — **Servizio TTS multi-motore + gestione lingue** (`app/tts.py`,
  `GET /tts` e `/tts/status`): la lingua instrada al motore via `tts.voice_it|en`
  (formato `motore:voce`) — **italiano = Piper** (`it_IT-paola-medium`, voce scaricata
  al primo uso in `tts_voices/`; fix macOS `SSL_CERT_FILE`→certifi), **inglese =
  KittenTTS**. Cache WAV su disco (atomica, `tts_cache/`), import pigri (503 spiegato),
  categoria admin «Voce», card Admin con anteprime audio. ⚖️ `piper-tts` è **GPL-3** →
  opzionale, MAI in requirements (progetto MIT): si abilita con `make piper`.
  144 test verdi (motori finti); dal vivo: it ~1s/frase, cache 0,09s.
- **2026-07-06** — **Istruzione guidata (tutorial)**: contenuti in `app/lessons/`
  (helper `sq`/`pos8`/`path_task`; corso scacchi 7 lezioni + dama + Tris; guardiano
  `validate_lesson` nei test), progressi per utente (`lesson_progress`, migrazione
  **0004**, `last_step` non regredisce), router `/lessons` (lettura aperta, progresso
  autenticato). UI «Impara»: indice con riprendi/completata, pagina lezione con la
  stessa scacchiera di gioco (CSS estratto in `board_css.html`, condiviso con
  play.html), evidenziazioni, verifica dei task, voce 🔊 via `/tts` + «voce
  automatica». 148 test verdi; verifica dal vivo completa.
- **2026-07-06** — **Stockfish processo persistente** (`_PersistentEngine`, singleton +
  lock): handshake `uci` una volta, opzioni di forza a diff (LimitStrength sempre
  esplicito: coi preset per lato vanno anche ripristinate), `ucinewgame` solo a partita
  nuova (hash calde nelle continuazioni), watchdog + respawn automatico su
  crash/timeout/cambio percorso, `quit` solo a shutdown (atexit; `shutdown()` per i
  test). `_uci_dialogue` one-shot resta SOLO per `verify()` (che ora riporta PID e
  ricerche servite). Finti motori dei test ora interattivi con log comandi. 151 test
  verdi; dal vivo: 6 mosse contro Pan, un solo PID.
- **2026-07-06** — **Sparring + analisi + moviola + GIF**: `evaluate()` sul motore
  persistente; `analysis.py` (job, errori ??/?/?! a 200/100/50 cp, cp lato bianco,
  cache in `analysis_json`, migrazione **0005**, param `stockfish.analysis_ms`);
  `sparring.py` (match a colori alternati vs preset a Elo noto, stima logistica ±
  margine, `POST/GET /admin/sparring`); moviola `GET /sessions/{id}/replay` +
  **note per mossa** dentro `moves_json` (`POST .../note`, solo partecipanti nei
  remote); GIF `GET /sessions/{id}/gif` (`gifexport.py`, **Pillow**, glifi da font di
  sistema + ripiego lettere, no backgammon). UI: pannello Moviola in play.html
  (⏮◀▶⏭, clic sul log, note, grafico SVG, GIF), card Sparring in Admin, note nello
  storico del giocatore. 156 test verdi; dal vivo l'analisi marca ?! su 1.f3 e ?? su
  3.g4 (matto dell'imbecille), GIF 464×464 valida.
- **2026-07-06** — **Apertura-bersaglio**: il libro indicizza (mossa, nome linea);
  `opening_move(prefer=…)` preferisce le linee delle `weakest_openings` del profilo
  avversario (sottostringa nei due sensi, ripiego su tutto il libro);
  `opponent_style` → `style["target_openings"]` → dispatcher (vale per ogni tipo di
  IA). 160 test verdi.
- **2026-07-06** — **Stima delle blunder**: `profile["accuracy"]` aggrega SOLO le
  analisi in cache (mai motore nel build: gira a ogni mossa) — ACPL (tetto 1000),
  blunder/errori/imprecisioni del lato del giocatore; `POST /users/{id}/analyze-history`
  riempie la cache in background (pulsante nella scheda). ≥20 mosse analizzate →
  debolezze («blunder frequenti», «precisione bassa») e aggressività +0,15·bpg
  (tetto 1,9). 161 test verdi; dal vivo acpl 539,5 su remoto_a.
- **2026-07-06** — **Hint riservato ai principianti**: `POST /sessions/{id}/hint`
  (motore locale, `hints.engine_ms`); negato oltre `hints.max_wins` vittorie nel
  gioco, nel formato FIDE (e nei futuri tornei/campionati), fuori turno; token nei
  remote; pulsante 💡 con evidenziazione. 164 test verdi.
- **2026-07-06** — **Triplice ripetizione**: `Chess.is_repetition_draw(history)`
  (chiave FIDE, storico rigiocato O(n)); dichiarata d'ufficio in `finish_if_terminal`
  (`finish_reason="repetition"`), automatica (non su richiesta) per evitare partite
  infinite. 166 test verdi; dal vivo `finished draw repetition`.
- **2026-07-06** — **Import libro da PGN**: `engine/chess/pgn.py` (SAN→UCI rigiocando
  col motore, match unico; pulizia commenti/varianti/NAG; una linea per partita,
  16 semimosse, nomi da Opening/ECO); `CHESS_BOOK_FILE` auto-riconosce il .pgn.
  Polyglot .bin rimandato (tabella Zobrist standard). 169 test verdi.
- **2026-07-06** — **Polyglot (.bin)**: `polyglot.py` + tabella RANDOM64 validata
  sui 9 vettori ufficiali; probing bisect, scelta pesata, arrocchi tradotti;
  `CHESS_POLYGLOT_BOOK` con priorità al libro interno (nomi/bersagli).
  172 test verdi.
- **2026-07-06** — **Badge qualità + commentatore LLM**: `commentary.py` dopo ogni
  mossa di scacchi (eval memoizzata per sessione, 1 ricerca/mossa) — 🌟👍⚔️🐔🤔😬🤡
  in `moves_json.quality`, battuta del provider attivo in `comment` (widget «🎙️»);
  badge sul pezzo mosso (.qbadge), interruttori commentary.enabled/llm. 174 verdi.
- **2026-07-07** — **Posizione morta FIDE + audit di conformità**: `_insufficient`
  corretta (bug: K+B+B vs K dichiarato patta con matto forzato disponibile!) — ora
  K vs K, K+minore, soli alfieri monotinta; Re+2C viva. Audit completo vs Laws of
  Chess: tabella in MANUAL con le semplificazioni dichiarate (ripetizione/50 mosse
  d'ufficio, bandierina=re nudo, morte non-materiali non rilevate); scoperte lacune
  → TODO: abbandono (5.1.2) e patta d'accordo (9.1). 177 test verdi.
- **2026-07-07** — **Abbandono + patta d'accordo**: `draw_offer` (migrazione 0006),
  `/sessions/{id}/resign` (re nudo → patta, come bandierina) e `/draw`
  (offer/accept/decline, mossa = rifiuto, offerta incrociata = accettazione, IA non
  tratta), `_acting_human` con token nei remote, `finish_manual`, guardia anti-corsa
  (refresh nel worker). Pulsanti 🏳️/½ + banner in partita. 180 test verdi;
  dal vivo `finished draw agreement`. Lacune FIDE dell'audit chiuse.
- **2026-07-07** — **Bandierina art. 6.9 piena**: `Chess.cannot_mate` (matti d'aiuto
  su materiale: impossibile solo re nudo / K+C vs nudo / alfieri monotinta bilaterali;
  K+2C vince a tempo); `_winner_on_time` la usa → vale anche per l'abbandono.
  182 test verdi. Tabella FIDE del MANUAL: semplificazione rimossa.
- **2026-07-07** — **Potenziamenti di ricerca**: SEE (swap+raggi X, pota catture
  perdenti in quiescence), PVS (nodi interni e radice, composto con LMR),
  aspiration windows (±50 cp, fail→ricerca piena, jitter-safe), futility a depth 1
  (statico+150, prima legale sempre cercata). Prof. 6: −36/−62/−65% di tempo,
  stesse mosse/punteggi. 185 test verdi (SEE su scambi noti, matto, donna salva).
- **2026-07-07** — **Finali**: mop-up (8·dist_centro + 5·vicinanza re, attivo con
  vantaggio ≥ torre su re quasi nudo) e KPK (quadrato col tempo, pedone di torre,
  re davanti; l'euristica SOSTITUISCE l'eval del finale). Self-play KQvK: matto in
  ~7 mosse. 188 test verdi; nodi identici fuori dai finali.
- **2026-07-07** — **Pondering**: `ponder.py` — thread che riempie una TT condivisa
  per sessione durante il turno umano (posizione, non ponderhit); `best_move`
  accetta `tt=`/`stop=`; start a turno umano, stop alla mossa (TT conservata,
  ~3× meno nodi), drop a fine partita; cap 400k, gate ponder.enabled+async,
  solo scacchi vs motore locale. 191 test verdi.
- **2026-07-07** — **Livelli di difficoltà del motore locale**: 5 preset
  (`local.ENGINE_LEVELS` — Maestro/Esperto/Medio/Apprendista/Novizio) con tempo e
  jitter crescente (0→300 cp); scavalcano il provider remoto; stessa colonna
  `*_ai_level` (no migrazione); voci «Motore — …» al setup; livelli deboli esclusi
  dal pondering. 197 test verdi.
- **2026-07-07** — **Export PGN + import FEN**: scrittore SAN nel motore
  (`pgn.uci_to_san`/`san_line`), `GET /sessions/{id}/pgn` (tag, SAN, note come
  `{…}`, SetUp/FEN); colonna `start_fen` (migrazione 0007) validata/normalizzata,
  campo FEN al setup; replay/analisi/commento/Stockfish/ripetizione ripartono
  dalla FEN (`stockfish.uci_position` unico). X = Bianco sempre. 208 test verdi.
- **2026-07-07** — **Arena IA**: `ai_arena.py` — identità per configurazione IA,
  Elo per (gioco, identità) in `ai_ratings` (1500/K=32, hook in
  `finalize_session`, solo IA-vs-IA); tornei round-robin (2-8, andata/ritorno)
  giocati in sequenza come vere sessioni; migrazione 0008; endpoint `/arena/*`;
  pagina «Arena IA» con dettaglio torneo in polling. 213 test verdi.
- **2026-07-07** — **Scacchiera da torneo**: cornice `.bframe` + helper JS
  `frameBoard` in board_css.html (bande 26px, filetto d'intarsio, coordinate
  A–H/1–8 solo scacchi, case a filo con selezione a ombra interna, colori per
  tema via --bframe/--binlay/--bcoord, WCAG ≥4.5:1); usata da play.html e
  learn_lesson.html. Solo frontend, 213 test verdi.
- **2026-07-07** — **Breaker + cifratura token**: `breaker.py` (3 errori → aperto
  120s, mezzo-aperto a sonda, scudo `api_ai.guarded_complete`, stato in
  list_providers + badge admin) e `token_crypto.py` (Fernet `enc:…` stessa
  colonna, chiave TOKENS_KEY o derivata da ADMIN_TOKEN via PBKDF2, migrazione
  lazy al seed, key_unreadable in lista). Dep nuova `cryptography`. 219 verdi.
- **2026-07-07** — **Cache profilo avversario**: `profile_cache.py` (copia per
  giocatore, invalidazione a eventi in finalize_session/analysis + TTL
  `profile.cache_ttl_s` 300s, 0=off; usata da opponent_style e dall'endpoint
  profilo; dict condiviso = immutabile). 222 test verdi.
- **2026-07-07** — **«Spiegami questa mossa»**: POST /sessions/{id}/explain
  (dati già prodotti: FEN, analisi, badge, apertura, nota → prompt istruttore
  ≤3 frasi via guarded_complete; salvata in moves_json[ply-1]["explain"],
  cached al secondo clic; coach.explain_enabled); pulsante 🎓 in moviola.
  226 test verdi.
- **2026-07-07** — **Tilt + bias**: `tilt.py` (sconfitte rapide consecutive +
  ACPL recente vs media; GET /users/{id}/tilt; banner soft nel setup; blocco
  SOLO opzione admin tilt.block con cooldown 30′) e `profile["biases"]`
  (donna precoce, re in centro, coazione cattura, monotonia apertura; ≥5
  partite/≥40%; scheda giocatore). GM-database resta ricerca. 233 verdi.
- **2026-07-07** — **Dama potenziata**: priorità FID complete sulle catture
  (cascata: pezzi → con la dama → più dame → dama prima), triplice ripetizione,
  motore dedicato `draughts/engine.py` (negamax iterativo + estensione catture,
  TT, jitter ×0,03) al posto del minimax profondità 4; euristica con trincea e
  centro. 241 test verdi.
- **2026-07-07** — **Scacchiera migliore**: drag&drop (pointer events, ghost,
  promozione, click post-drop soppresso), ultima mossa evidenziata (live e
  moviola), rotazione via CSS `order` (DOM in ordine di scacchiera: flyer/badge
  intatti; auto-flip Nero remoto + 🔄; coordinate che seguono), pannello catture
  con bilancio (+n; nascosto da FEN). Solo frontend, 241 verdi.
- **2026-07-08** — **Promozione grafica**: choosePromotion → Promise + overlay
  sulla griglia (bottoni ♛♜♝♞ con classi .cell → colori tema gratis; Esc/fuori
  = annulla; tasti q/r/b/n); resolvePromotion nei due chiamanti; guardia dama
  (percorsi equivalenti ≠ promozione). Solo frontend, 241 verdi.
- **2026-07-08** — **Responsive mobile**: media query base.html (nav compatta,
  tabelle scorrevoli, anti-zoom iOS), fitCellPx condiviso (scacchiera che entra
  nello schermo, play+lezioni), rimisura al resize con guardie busy/drag,
  cornice sottile ≤480px. Accessibilità (tastiera/ARIA) scorporata nel TODO.
  Solo frontend, 241 verdi.
- **2026-07-08** — **A11y + i18n**: caselle con aria-label localizzate, roving
  tabindex + frecce (vista-aware), aria-live, dialog promozione accessibile;
  i18n Django (LocaleMiddleware, selettore IT/EN in nav, stringhe JS via
  views._play_ui_strings → json_script, label form gettext_lazy, catalogo EN
  67 msgid compilato). Seconda tranche (pagine secondarie/backend) nel TODO.
- **2026-07-08** — **i18n tranche 2**: tutti i template marcati (JS compreso,
  pattern generici anti-collisione HTML/JS), catalogo EN ~170 msgid, fuzzy di
  msgmerge corretti (gettext li ignora a runtime!), smoke 12 pagine IT/EN.
  UI interamente bilingue; resta «i18n (dati)» (backend/lezioni/aperture).
  241 verdi.
- **2026-07-08** — **i18n dati (backend)**: middleware Accept-Language →
  ContextVar, `_()` alla risposta (DB in italiano), catalogo dict 208 voci
  (~76 detail, tilt, ~45 etichette admin, 90 aperture EN standard, profilo
  alla frontiera con regex per le debolezze parametrizzate); api_client
  inoltra la lingua. Trappola: `for _ in` ombreggia `_`. Resta «i18n
  (contenuti)» (lezioni). 247 verdi.
- **2026-07-08** — **Rating Elo umano**: `rating.py` + tabella `ratings`
  (migrazione 0009), K adattivo FIDE (40/20/10, provvisorio <30), solo partite
  umano-vs-umano (pool separato dall'arena IA), stagioni via `elo.season`
  (storico con ?season=); classifica in pagina Classifiche + card nella scheda.
  Bugfix: score_for senza flush duplicava scores (autoflush=False). 253 verdi.
- **2026-07-08** — **Rinomina: Scacchi → OmniBoard** (progetto, non il gioco):
  repo GitHub `saulusprime/OmniBoard` (redirect dal vecchio), package
  `omniboard_web`, brand/titoli/API/site_name/PGN Event, DB `omniboard.db`
  (copia; .env aggiornato). Cartella locale invariata (venv con shebang
  assoluti). 253 verdi.
- **2026-07-08** — **SQLAlchemy 2.0 tipizzato**: DeclarativeBase +
  Mapped[]/mapped_column ovunque (relazioni tipizzate); nullabilità fedele
  nelle annotazioni (attenzione ai nullable per omissione); tipi SQL espliciti;
  `alembic check` = zero differenze. Dev-DB ristampato a 0009 (il reload aveva
  applicato l'ID autogenerato pre-rinomina). 253 verdi.
- **2026-07-08** — **Coda mosse IA**: `jobqueue.py` (pool limitato ai.workers=2,
  enqueue idempotente, recovery_scan al lifespan — il DB è lo stato durevole
  dei job, GET /admin/jobs). **ADR: RabbitMQ scartato** (seconda fonte di
  verità + footprint; a multi-processo → Postgres SKIP LOCKED o Redis/RQ
  dietro la stessa interfaccia). 258 verdi.
- **2026-07-08** — **Statistiche avanzate + mosse geniali**: `insights.py`
  (per-gioco con Elo e serie, esiti scacchi, badge propri; brilliancies 🌟 con
  avversario/esito/data), `GET /sessions/{id}/board.png?ply=` (render_png dal
  renderer GIF), pagina `/giocatori/<id>/statistiche/` con galleria. 💎
  sacrifici e salto moviola ?ply= restano nel TODO. 262 verdi.
- **2026-07-08** — **Mosse geniali, raffinamenti**: badge 💎 (sacrificio) via
  replay + SEE avversaria ≥200cp (commentary._is_sacrifice, solo su perdita
  ≤30); filtri galleria tipo+pezzo; moviola ?ply=N. Emoji nei sorgenti:
  replace per riga (variation selector). 265 verdi.
- **2026-07-08** — **Sistema PUZZLE** (primitiva Visione): tabelle
  puzzles/puzzle_attempts (migr. 0010), seed autoriale verificato col motore
  (idempotente per FEN), generazione dai «??» (confutazione motore 0,8s,
  dedup partita+semimossa), check_attempt stateless con matto alternativo,
  pagina elenco+player. Sblocca tilt-breaker/Gatekeeper/Puzzle Story.
  270 verdi.
- **2026-07-08** — **Prestazioni per cadenza**: insights.by_cadence
  (tc_category, V/P/S + ACPL proprie mosse, ordine fisso) + tabella nelle
  Statistiche. Trappola .po: msgstr multiriga + regex a riga singola =
  traduzioni concatenate. 271 verdi.
- **2026-07-09** — **Quattro aspetti del gioco**: insights._aspects dalle
  analisi in cache — aperture (ACPL prime ~12 mosse + libro ¼), tattica
  (blunder commessi/puniti), strategia (ACPL mosse quiete del mediogioco),
  finali (ACPL con ≤6 pezzi non-pedone). Fasi da replay deterministico
  (_phases, MAI ricerca); punteggi 0-100 euristici, None sotto campione
  minimo. Riquadri con barre nelle Statistiche, bilingue (occhio: l10n IT
  rende 48.3 → «48,3» nei template). In apertura di sessione: fix
  alembic_version stantia (0ea7a8c15601 → 0010, trappola rinomina). 273 verdi.
- **2026-07-09** — **Gruppi (gestione) e Tornei umani** (migr. 0011): inviti
  con accettazione (riga unica per gruppo+utente, re-invito → pending), ruoli
  founder/admin/member, espulsioni graduate, classifica interna;
  human_tournaments.py — knockout (seed da Elo, bye, bracket classico, patta
  → passa il Nero/draw odds) e girone; partite = vere GameSession, hook
  record_result in finalize_session (senza commit), pagine Tornei col
  tabellone. FIX I18N STRUTTURALE: l'alias `_t` non è keyword di xgettext →
  le stringhe di views.py non venivano MAI estratte; rinominato in `_`
  (ora makemessages estrae tutto; 41 fuzzy sciolti, ~60 voci riempite per
  blocchi interi). 277 verdi.
- **2026-07-09** — **Notifiche e inviti a giocare** (migr. 0012): sfide come
  inviti (`/challenges`: gioco/lato/cadenza validata subito; accettare crea la
  GameSession remote con orologio); notifiche persistenti kind+parametri con
  testo composto ALLA LETTURA (template in notifications._TEMPLATES +
  catalog_en), notify() senza commit, pota le lette oltre 50; campanella 🔔 in
  navbar dal heartbeat; hook su inviti gruppo, nuovo turno e fine torneo.
  Trappola: col cookie firmato il test client Django non salva la sessione da
  solo (impostare client.cookies[SESSION_COOKIE_NAME]). 282 verdi.
- **2026-07-09** — **Sfide gruppo-vs-gruppo** (migr. 0013): squadre a
  tavoliere multiplo (1-8) via group_matches.py + /group-matches — propone e
  risponde un manager; formazioni AUTOMATICHE per Elo (tavolo 1 = il più
  forte; membri comuni ai DUE gruppi esclusi, organico contato sugli
  eleggibili), colori alternati per tavolo, 1/½ per tavolo, parità legittima
  (winner_group_id None); verdetto+notifiche a fine tavoli (hook in
  finalize_session). Bilancio V/N/P nella scheda gruppo. NB: le sessioni dei
  tavoli sono remote=True → nelle prove le mosse vogliono il token di chi
  muove (quelle dei tornei sono hotseat). 285 verdi.
- **2026-07-09** — **Spettatori e replay animato**: GET /community/live
  (criterio di sicurezza: solo remote — azioni protette dal token — e
  IA-vs-IA; hotseat MAI esposte) + pagina watch.html a doppia modalità:
  diretta (polling stato.json 3s) e replay animato (fotogrammi da /replay
  già esistente, controlli play/pausa/velocità/slider). Renderer scacchiera
  di sola lettura copiato dal client di play (SOLID_GLYPH, pieceClass
  sull'ultimo carattere, classi per gioco). Sezione dirette in Community nel
  polling esistente; link «Replay animato» negli export post-partita.
  287 verdi.
- **2026-07-09** — **CI GitHub Actions completa**: riscritto il ci.yml
  «tollerante» dell'era doc-only. Checkout con submodule (KittenTTS è in
  backend/requirements.txt come ./integrazioni/KittenTTS: pip DALLA ROOT),
  apt stockfish+gettext, ruff check+format, msgfmt sul .po, alembic
  upgrade+check su DB VERGINE (gate contro la trappola delle migrazioni
  rinominate), pytest completo (conftest autosufficiente: nessun .env o
  segreto in CI, i settings hanno default). Badge CI nel README. Primo run
  VERDE su main in 2m20s (i run precedenti fallivano al pip: checkout senza
  submodule → ./integrazioni/KittenTTS vuota).
- **2026-07-11** — **Sottocategorie tattiche**: tactics.subcategories nei
  quattro aspetti — per ogni mossa che concede ≥250 cp (perdita GREZZA):
  matti mancati (|cp|≥9901 prima e non dopo, cp della semimossa precedente;
  classificati PRIMA: le loro perdite sono giganti), pezzi in presa (risposta
  reale = cattura, taglie da perdita 250/450/850), scacchi concessi (scacco
  puro), tattiche silenziose (risposta quieta), catture avvelenate
  (trasversale: la mossa concedente era una cattura). Senza risposta →
  contata ma non classificata. Riga «Dettaglio tattico» in Statistiche.
  288 verdi.
- **2026-07-11** — **Confronto coi pari fascia**: insights.peer_comparison —
  fascia Elo 200pt dal rating stagionale (1500 i non classificati), ACPL e
  blunder/partita per TUTTI in un solo passaggio sulle analisi (niente
  replay per i pari, tetto 2000 sessioni); better_than = quota di pari
  STRETTAMENTE peggiori; percentile solo con ≥3 pari da ≥20 mosse. Nei test
  la fascia va ISOLATA (Elo iniettati 2250-2350): gli utenti ~1500 degli
  altri test inquinerebbero il campione. FLAKE sistemato in
  test_async_move_executed_by_the_pool: il worker della coda poteva giocare
  la mossa IA fra commit e serializzazione della risposta → cancello
  (threading.Event) prima del processing. 289 verdi.
- **2026-07-11** — **CHECKPOINT anti-compattazione**: fotografia completa in
  HANDOFF (voce autosufficiente); README riallineato (stato con community/CI,
  migrazioni 0013, moduli/router nuovi nell'albero, 3 voci roadmap stantie
  spuntate: Elo, gestione gruppi, regole dama); questioni aperte aggiornate
  (WebSocket ora il candidato più maturo; + recency e massa giocatori); TODO
  arricchito della voce WebSocket esplicita; memoria persistente riscritta
  allo stato corrente con le trappole nuove (fasce isolate nei test, cancello
  del worker, cookie firmato nei test Django, alias `_` per xgettext).
- **2026-07-11** — **Forza 4: motore dedicato bitboard**
  (`engine/connect4/engine.py`, agganciato via `engine_move`): bitboard alla
  Fhourstones (7 bit/colonna con sentinella, chiave TT `position+mask`),
  negamax con TT a flag, tattica ESATTA a ogni nodo (vittoria immediata,
  doppia minaccia = sconfitta, blocco forzato, mai sotto una casella vincente
  avversaria), approfondimento iterativo con budget, jitter ×0.16. BUG DI
  RADICE scovato e corretto ANCHE NELLA DAMA: finestra `(-∞,-alpha)` senza
  margine → una mossa che fallisce alto al confine registra un bound pari ad
  alpha → falso pareggio col migliore → il sorteggio del pool poteva scegliere
  una mossa persa (il greedy a 1 mossa batteva il motore 2/12!). Fix: margine
  `int(jitter)+1` sulla beta di radice; dopo, 20/20 contro il greedy. Ricerca
  verificata con cross-check contro un negamax di riferimento nudo (valori
  identici su 30 posizioni × profondità 2/4). 296 verdi.
- **2026-07-11** — **Backlog diviso in due file**: le 69 voci `[x]` di TODO.md
  spostate (testo intatto, stesse sezioni) nel nuovo **ASIS.md**; in TODO.md
  restano le 21 aperte. Flusso nuovo nell'intestazione di TODO: a voce
  realizzata → spostarla in ASIS.md e documentarla in HANDOFF. Puntatori
  aggiornati in README e memoria persistente.
- **2026-07-11** — **Forza 4: tavoliere dedicato + accessibilità**: classe
  `.c4-board` (blu coi fori, dischi rossi ✕ / gialli ◯ — marchio inciso sul
  ::after contro il solo-colore, WCAG 1.4.1), anteprima della caduta su
  hover/fuoco, anello sull'ultima mossa (il disco nuovo è il più ALTO della
  colonna), quaterna vincente pulsante (rispetta prefers-reduced-motion),
  destinazione `inflight` durante il volo del disco. Celle = BOTTONI (clic =
  colonna, frecce+Invio, ARIA «riga R, colonna C, pedina rossa/gialla», nuove
  stringhe c4_red/c4_yellow, .po a mano + msgfmt). fitCellPx con `extra`
  (+44px di contorno tavoliere) e `width:max-content` (allagava la pagina
  spettatore). Verificato DAL VIVO con Chrome headless su partita IA-vs-IA
  (il ripiego usa il motore bitboard). Trappola: sotto ~500px l'headless non
  restringe il viewport, ritaglia — misurare con --dump-dom. 297 verdi.
- **2026-07-11** — **Fix deformazione tavoliere Forza 4** (segnalato
  dall'utente): `position:relative` applicato per errore anche al `.flyer`
  (raggruppato con `.cell` nella regola `.c4-board`) lo faceva entrare nel
  flusso della griglia → riga fantasma in basso durante l'animazione di
  caduta. Fix: relative solo sulle celle, il flyer resta absolute. TRAPPOLA
  CSS: mai regole di `position` raggruppate su .cell e .flyer. Verificato con
  harness statico sul CSS servito (394px con e senza flyer). 297 verdi.
- **2026-07-11** — **Othello e Gomoku** (6º e 7º gioco): Othello con **passo
  automatico dentro apply** (legal_moves mai vuota su posizione viva: il
  client ignora il "passo"; ADR implicito: niente mossa esplicita di passo),
  Nero=lato X=●, conta pedine in view_status, euristica posizionale
  (quarto 4×4 specchiato) per il minimax generico depth 4. Gomoku col motore
  dedicato (candidati Chebyshev≤2, tattica esatta, valutazione a finestre di
  5 con delta incrementale, iterativo con margine sul jitter) — il generico
  non regge 225 rami. Piattaforma: seed idempotente 7 giochi, GIF con dischi
  ●/○, client con `legalCells` (nell'Othello le vuote non giocabili sono
  DISABILITATE, col puntino sulle legali). Verificato dal vivo (IA-vs-IA:
  Othello 40-24, Gomoku col motore interno). 318 verdi.
- **2026-07-11** — **Accessibilità per tutti i giochi**: coordinate attorno ai
  tavolieri coerenti con la notazione del log (`gameCoords`+`coordFrame`
  condivisi in board_css.html, strisce allineate via gap/inset del tavoliere:
  Othello a1-h8, Gomoku a1-o15, Tris a1-c3, Forza 4 colonne 1-7, backgammon
  punte 13-24/12-1 + B/U dal punto di vista del Bianco). FIX STRUTTURALE
  tastiera: celle `disabled` = infocalizzabili → frecce bloccate; ora
  `aria-disabled`+`.cell-off` (griglia sempre esplorabile, azione impedita
  dalle guardie nei gestori — onCell controlla legalCells). TRAPPOLA: mai
  `disabled` sui bottoni-cella dei tavolieri; CSS con `:not(.cell-off)` al
  posto di `:enabled`. ARIA = notazione («d3, pedina nera», «punta 13»).
  Flake del greedy Forza 4 → al meglio di tre (patta tollerata, sconfitta
  mai). 318 verdi.
- **2026-07-11** — **Piano di riorganizzazione del frontend** (solo analisi,
  scritta nel TODO come sezione ⭐): modello chess.com — 5 aree per OmniBoard
  (Gioca/Puzzle/Impara/Guarda/Community), navbar con menu a discesa + landing
  di area, avatar col menu profilo (Admin dentro), campanella con pannello
  notifiche proprio, home-dashboard per il loggato; la pagina Community si
  smembra (dirette→Guarda, sfide→Gioca, notifiche→campanella). Cinque fasi
  nel TODO; vincoli: URL conservati, heartbeat intatto, i18n.
- **2026-07-11** — **Frontend Fase 1 (navigazione) FATTA**: navbar a 5 aree
  con menu disclosure accessibili (aria-expanded, Esc, hover solo con
  `(hover:hover)`), hamburger mobile, menu profilo sull'avatar (Admin dentro:
  nel backend il super admin è un TOKEN, non un flag utente — il link non è
  condizionabile), campanella con pannello da `notifiche.json` (URL risolti
  lato server con reverse(), MAI pattern di URL nel JS) che segna lette
  all'apertura. Ancore di sezione in community.html come landing provvisorie
  delle aree. 320 verdi. Restano le fasi 2-5.
- **2026-07-11** — **Frontend Fase 2 (hub «Gioca») FATTA**: /gioca/ = landing
  d'area (azioni, partite in corso con riprendi, sfide accetta/rifiuta,
  tornei aperti), setup su /gioca/nuova/ con lo STESSO nome di rotta
  play_setup (i reverse seguono da soli); challenge_action → hub. TRAPPOLA
  (x2): i mock dei test devono avere la FORMA VERA del payload — la lista
  nuda al posto di {"tournaments": []} aveva nascosto un crash che solo la
  verifica dal vivo ha scovato; e dopo un fix il runserver --noreload va
  RIAVVIATO (il debug page mostra il sorgente nuovo ma esegue il bytecode
  vecchio: traceback fantasma). 321 verdi. Restano le fasi 3-5.
- **2026-07-11** — **Frontend Fase 3 (hub «Guarda») FATTA**: /guarda/ =
  dirette auto-aggiornate + tornei Arena IA + replay recenti; backend nuovo
  GET /community/recent (ultime 10 concluse, stessa platea `_WATCHABLE` delle
  dirette — filtro e `_side_label` ora condivisi fra live e recent). Nota di
  metodo: un «baco» dell'esito nei replay era una SESSIONE DIVERSA con lo
  stesso gioco (l'utente aveva giocato altre IA-vs-IA) — controllare l'id
  della riga prima di inseguire il template. 322 verdi. Restano le fasi 4-5.
- **2026-07-11** — **Frontend Fase 4 (Community ristretta) FATTA**: community
  = landing d'area (online + rimandi Giocatori/Gruppi/Classifiche); sezioni
  smembrate negli hub; pagina NUOVA /notifiche/ (elenco completo, marca-letto
  all'apertura, bersaglio della campanella; il marca-letto NON sta più nella
  community). community_json senza my_games: una query in meno a ogni
  heartbeat. challenge_new → hub Gioca. 322 verdi. Resta la Fase 5 (home
  dashboard).
- **2026-07-11** — **Frontend Fase 5 (home-cruscotto) FATTA — riorganizzazione
  chess.com COMPLETA in 5 fasi**: home a due volti (vetrina anonimi, cruscotto
  loggati: saluto, azioni, sfide/notifiche coi conteggi, riprendi, dirette).
  Verificata con LOGIN VERO (utente demo via API + client Django). NOTA: il
  .env sta nella ROOT del repo, non in backend/. Nel TODO restano solo le
  rifiniture (ricerca in navbar, breadcrumb). 323 verdi.
- **2026-07-11** — **Rifiniture frontend FATTE — sezione riorganizzazione
  CHIUSA**: ricerca giocatore in navbar (?q= su /giocatori/, filtro alias o
  nome, match unico → redirect alla scheda) e breadcrumb d'area su 18
  sottopagine (blocco breadcrumb + .crumbs in base.html; le landing non lo
  hanno: sono l'area); uscita dello spettatore → Guarda. 324 verdi.

## Questioni aperte

> Aggiornate al 2026-07-11 (le storiche — auth, notazione, ORM/Alembic, rendering
> scacchiera — sono tutte RISOLTE: v. milestone sopra).

- **Multi-processo/produzione**: SQLite→Postgres, coda mosse IA su SKIP LOCKED o
  Redis/RQ (interfaccia già pronta in `jobqueue.py`), TOKENS_KEY fissa in .env.
- **WebSocket** al posto del polling — ormai il candidato più maturo: oggi il
  polling regge mosse a distanza, presenza, campanella delle notifiche, dirette
  degli spettatori e tabelloni dei tornei (tanti giri per la stessa verità).
- **i18n (contenuti)**: traduzione editoriale delle lezioni; lingue oltre l'inglese.
- **Rate limiting + CORS espliciti** e **audit log** delle operazioni super admin.
- **Retro-etichettatura 💎**: le partite analizzate PRIMA del badge sacrificio non
  hanno diamanti (servirebbe un re-scan batch dei badge).
- **Recency**: unica voce ricerca degli Insights rimasta (punteggi aggregati con
  decadimento esponenziale sulle partite vecchie).
- **Massa di giocatori**: pari fascia e sfide di gruppo sono pronti ma rendono
  con più utenti attivi (percentili sotto i 3 pari restano None per onestà).
