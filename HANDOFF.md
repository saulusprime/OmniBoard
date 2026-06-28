# HANDOFF — Storico delle sessioni di lavoro

> Registro cronologico di tutte le sessioni e delle operazioni compiute.
> **La voce più recente è in cima.** Ogni voce descrive contesto, decisioni e modifiche.

---

## 2026-06-28 — IA scacchi: modello dell'avversario (schemi e debolezze dallo storico)

**Obiettivo:** far sì che l'IA analizzi lo **storico delle partite dell'avversario** per
identificarne schemi e debolezze e adattare il proprio gioco. (Secondo filone richiesto.)

**Realizzato:**
- **Profilazione** `backend/app/chess_profile.py`: `build_profile(db, user_id)` legge le partite
  di scacchi **concluse** del giocatore e calcola: bilancio per colore, **aperture giocate** con
  rendimento (via `openings.detect_opening`), durata media, **sconfitte rapide** (fragilità
  tattica), **tasso di patte**, durata media delle sconfitte (debolezza nei finali). Da qui deriva
  un elenco di **debolezze** leggibili e i parametri di **stile** per il motore:
  `aggression` (sale se l'avversario crolla presto → attaccare di più) e `contempt` (sale se patta
  spesso → evitare le semplificazioni).
- **Motore**: `contempt` reso semanticamente corretto (la patta è valutata rispetto al **lato
  dell'IA alla radice**, non al Bianco), applicato a patte per 50 mosse/materiale e **stallo**.
  `aggression` pesa la sicurezza del re. (contempt 0 / aggression 1 = comportamento invariato.)
- **Integrazione** (`sessions._opponent_style`): quando l'IA gioca a scacchi contro un **umano**,
  costruisce il profilo dell'avversario e passa lo `style` a `choose_move` (e quindi al motore).
- **API/Frontend**: `GET /users/{id}/chess-profile`; la scheda giocatore mostra un pannello
  «Profilo scacchistico (usato dall'IA)» con debolezze, aperture e stile adattato.
- **Test** `backend/tests/test_chess_profile.py`: utente inesistente → None; profilo vuoto neutro;
  rilevamento debolezze + stile (fragilità tattica → aggressività; patte → contempt); endpoint.
  **79 test** verdi; lint pulito.

**Verifiche dal vivo:** lo `style` derivato dal profilo arriva fino al motore (sorgente
`"engine"`); profilo calcolato correttamente su partite sintetiche.

**Possibile evoluzione:** scelta dell'**apertura-bersaglio** (giocare le linee in cui l'avversario
rende peggio) e stima delle *blunder* con rianalisi del motore su un campione di posizioni.

---

## 2026-06-28 — IA scacchi potenziata: motore di ricerca dedicato (alpha-beta forte)

**Obiettivo:** potenziare il più possibile l'IA degli scacchi — analizzare tutta la scacchiera
mossa dopo mossa e confrontarsi con gli schemi principali. (Primo dei tre filoni richiesti; il
modello dell'avversario è lo step successivo.)

**Scelta di fondo:** per gli scacchi un motore **alpha-beta locale** è molto più forte di una
singola mossa chiesta a un LLM via prompt. Quindi la potenza si costruisce sul **motore locale**,
non sulla chiamata remota.

**Realizzato:**
- **Nuovo motore** `engine/games/chess_engine.py`: **iterative deepening** con budget di tempo,
  **alpha-beta** (negamax) con **transposition table** (riconosce posizioni per trasposizione),
  **quiescence search** (estende catture/promozioni e tutte le mosse sotto scacco → niente
  *horizon effect*, l'IA non regala più pezzi), **ordinamento mosse** (TT, MVV-LVA, killer,
  history) per più tagli/profondità, **valutazione ricca** (materiale + tabelle posizionali per
  fase, pedoni doppiati/isolati/passati, coppia alfieri, torri su colonna aperta, sicurezza del
  re, tempo). Parametri di **stile** (contempt/aggression) come gancio per il profilo avversario.
- **`Chess.engine_move`** e **`Chess.from_fen`** (parser FEN, utile a test/analisi) in
  `engine/games/chess.py`.
- **Integrazione** (`backend/app/ai.py`): `choose_move` ora fa **libro → motore dedicato →
  provider remoto → locale**; per gli scacchi usa il motore (sorgente `"engine"`), che ha
  precedenza sull'LLM. Budget configurabile (`ai.engine_ms`, default 2000 ms; tetto operativo
  via `AI_ENGINE_MS_MAX`). Piccolo **jitter** alla radice per variare tra partite senza perdere
  forza (decisivo nel batch IA-vs-IA, motore altrimenti deterministico).
- **Setting** `ai.engine_ms` (categoria IA) nel super admin; sessioni e batch passano il budget.
- **Test** `backend/tests/test_chess_engine.py`: matto in 1, cattura di donna indifesa, **evita
  la cattura perdente** (quiescence), scacco-non-matto, determinismo, rispetto del tempo. **75
  test** verdi; lint pulito.

**Verifiche dal vivo:** apertura dal libro (`e2e4`); da posizione iniziale gioca `Nc3` entro 2s;
in una posizione tattica trova `Qd8+!!` (sacrificio di donna che forza il matto del corridoio) in
0.01s — irraggiungibile dal vecchio minimax solo-materiale (profondità 3).

---

## 2026-06-28 — Fix freeze del backend: chiamata IA remota inline + auto-attivazione Qwen

**Sintomo:** di nuovo *Bad Request* su `…/mossa.json` (sessione 18) e backend che smette di
rispondere a **tutti** gli endpoint (anche `/health`).

**Diagnosi (verificata):** sessione 18 = scacchi, Nero (umano) **sotto scacco** dopo `Bb5+` →
il 400 era la risposta **corretta** a una mossa non legale. La causa profonda era un **freeze del
backend**: il worker uvicorn aveva due connessioni TCP **`SYN_SENT`** verso l'endpoint Qwen su
**IPv6** (`240b:…`, rete cinese) irraggiungibile dall'Europa. Avendo io **auto-attivato Qwen**
dal `.env` (vedi voce precedente), ogni turno IA chiamava il provider remoto **in linea** nella
richiesta di mossa; `httpx` (client sync, senza Happy Eyeballs) tentava prima l'IPv6 e restava
appeso nel connect. Le chiamate si accumulavano e il backend si bloccava; la `resync()` del
client non riusciva più a raggiungerlo, lasciando mosse legali **stale** → 400 sulla mossa ormai
illegale. (Qwen è comunque inutilizzabile: 403 `insufficient_quota`.)

**Correzioni:**
1. **Niente auto-attivazione** (`ai_providers.seed_providers`): la preregistrazione via `.env`
   **memorizza** il token ma non rende attivo il provider. L'attivazione è una scelta **esplicita**
   dal super admin (un provider non verificato — token errato, quota esaurita, endpoint
   irraggiungibile — non deve far partire chiamate remote a ogni mossa).
2. **Timeout di connect breve** (`ai._http_timeout`, `httpx.Timeout(total, connect=min(4, total))`)
   per le chiamate OpenAI-compatible e Anthropic: un endpoint che non risponde fallisce in fretta
   e si ripiega sul giocatore locale, invece di bloccare la richiesta.
3. **Qwen disattivato** nel DB di sviluppo (`ai.provider=""`): l'IA usa il **giocatore locale**
   (immediato). Resta riattivabile da `/admin/ia/` quando si abiliterà l'accesso a pagamento.

**Test:** aggiornati i test del seed (memorizza senza attivare; backfill senza attivazione).
**68 test** verdi; lint pulito.

**Verifiche dal vivo:** dopo il fix, `GET /sessions/18` risponde in **~14ms** (prima si bloccava);
mossa illegale → 400 `{"detail":"Mossa non valida"}` (corretto); su sessione scacchi nuova, mossa
legale `e2e4` → **200 in ~0.02s** con risposta IA locale immediata. Le 6 parate legali allo scacco
in sessione 18 sono `b8d7, b8c6, c8d7, d8d7, e8e7, c7c6`.

**Nota frontend:** la scacchiera restringe già la selezione alle mosse legali del server e si
risincronizza (`resync`) su errore; falliva solo perché il backend era congelato. Nessuna modifica
frontend necessaria.

---

## 2026-06-28 — `.env` di test + preregistrazione Qwen (backend legge `.env`)

**Obiettivo:** creare un `.env` di sviluppo con la **configurazione Qwen preregistrata**,
tenendolo fuori dal versionamento (`.gitignore`) per non diffondere l'API key.

**Realizzato:**
- **`.env`** creato in root (coperto da `.gitignore`, **non** tracciato — verificato con
  `git check-ignore`): provider Qwen del workspace Aliyun (`QWEN_API_KEY`, `QWEN_BASE_URL`
  del workspace `ws-…maas.aliyuncs.com/compatible-mode/v1`, `QWEN_MODEL=qwen-plus`,
  `AI_TIMEOUT`) + segreti casuali per `SECRET_KEY`/`ADMIN_TOKEN`/`DJANGO_SECRET_KEY`.
- **Il backend ora carica `.env`** (`backend/app/__init__.py`, `load_dotenv` con
  `override=False`, eseguito prima di ogni altro import perché i moduli leggono `os.getenv`
  all'import). Prima solo il frontend Django lo faceva: senza questo, la preregistrazione via
  `.env` non avrebbe raggiunto il backend.
- **Seed più robusto** (`ai_providers.seed_providers`): la migrazione del token Qwen da ambiente
  avviene anche in **backfill** su un DB già esistente *se* Qwen non ha ancora un token (senza
  sovrascrivere quanto impostato da UI); alla **prima adozione** del token, se nessun provider è
  attivo, **Qwen viene attivato** in automatico. Così avviare il backend con il `.env` rende
  l'IA Qwen subito attiva.
- **Test ermetici** (`conftest.py`): `QWEN_API_KEY`/`DASHSCOPE_API_KEY` forzati a vuoto prima
  dell'import dell'app, così un `.env` reale non innesca migrazioni o chiamate di rete nei test.
  Aggiunti 3 test del seed (migrazione+attivazione, backfill su riga esistente, nessuna
  riattivazione se l'utente ha disattivato l'IA). **69 test** verdi; lint pulito.

**Verifiche dal vivo:** avviato il backend con il `.env` (DB nuovo) → `GET /admin/ai-providers`
mostra `active=qwen`, `has_key=true`, endpoint del workspace, `model=qwen-plus`, **token non
esposto**. Verifica connessione reale: la chiave **autentica** (`GET …/models` → 200, modelli del
workspace elencati, incl. `qwen-plus`), ma la chat ritorna **403 `insufficient_quota`** —
*«The free tier of the model has been exhausted… disable "use free tier only" mode»*.

**Conclusione:** configurazione corretta e cablaggio end-to-end funzionante; per giocare davvero
contro Qwen occorre **abilitare l'accesso a pagamento** (disattivare la modalità solo-free-tier)
nella console Alibaba Model Studio, oppure attendere il reset della quota. Finché la quota è
esaurita, l'IA ripiega in automatico sul **giocatore locale** (minimax alpha-beta).

---

## 2026-06-28 — Login provider IA: token configurabili da super admin (Qwen/Claude/OpenAI)

**Obiettivo:** invece di modificare a mano il `.env` per inserire `QWEN_API_KEY`, costruire
un'interfaccia di login verso **uno o più servizi IA** (Qwen, Claude, …) che autoconfigura il
token salvandolo lato server.

**Realizzato:**
- **Backend** (`backend/app/ai_providers.py`, nuovo): registro dei provider noti
  (`qwen` → OpenAI-compatible DashScope; `anthropic` → Claude via SDK; `openai`), tabella
  `ai_providers` (codice, etichetta, tipo, base_url, modello, **token**, aggiornamento).
  `seed_providers` popola i provider al primo avvio e **migra** un eventuale `QWEN_API_KEY` da
  ambiente (chi usava il vecchio metodo passa al nuovo senza riconfigurare). Nuovo parametro
  `ai.provider` (provider attivo) in `settings_service`. `get_active_config` fornisce all'IA la
  config del provider attivo (con token) o `None`.
- **IA** (`backend/app/ai.py`, riscritto multi-provider): `choose_move(..., provider=...)`
  ordine **libro → provider remoto → locale**. Dispatch per `kind`: `openai` via `httpx`
  (Qwen/OpenAI), `anthropic` via **SDK ufficiale** `anthropic` (no `temperature` su modelli 4.x,
  `max_tokens=64`, gestione `stop_reason == "refusal"`). `ping(provider)` verifica le credenziali.
- **API admin** (`routers/admin.py`): `GET /admin/ai-providers` (lettura aperta, **senza token**),
  `PUT /admin/ai-providers` (protetto `X-Admin-Token`), `POST /admin/ai-providers/{code}/test`
  (protetto) per verificare la connessione. **Sicurezza:** il token non è MAI restituito
  dall'API — si espone solo `has_key`; in scrittura un campo token vuoto **mantiene** quello
  esistente.
- **Frontend**: pagina **«Provider IA»** (`/admin/ia/`, `admin_ai`) con un riquadro per provider
  (radio «attivo», base URL, modello, token in campo password con badge «configurato»), pulsante
  **«Verifica connessione»** e token super admin per salvare; collegata da `/admin/`.
- **Sessioni**: mossa singola e batch IA-vs-IA leggono il provider attivo
  (`ai_providers.get_active_config`) e lo passano a `choose_move`.
- **Config**: `QWEN_API_KEY` nel `.env` ora è **opzionale** (configurabile da UI); aggiunta
  dipendenza `anthropic>=0.40` (`backend/requirements.txt`).
- **Test** (`backend/tests/test_ai_providers.py`, nuovi): provider seedati senza leak del token,
  scrittura protetta da token, salvataggio chiave + provider attivo senza leak, endpoint di test
  che segnala il token mancante (nessuna rete nei test). **66 test** verdi; lint `ruff` pulito.

**Verifiche dal vivo:** `GET /admin/ai-providers` non espone `api_key`; `PUT` senza token → 401;
`PUT` con token configura Qwen e lo attiva (risposta con `has_key=true`, niente token); endpoint
di test su `anthropic` senza token → `ok=false`; `/admin/ia/` resa e collegata da `/admin/`.

**Nota sicurezza (sviluppo):** i token sono salvati **in chiaro** nel DB (scaffold di sviluppo);
in produzione vanno cifrati / messi in un secret manager.

---

## 2026-06-28 — Fix: "bad request" su mossa.json (IA remota + desync)

**Sintomo:** in una partita di scacchi (sessione 13), dopo alcuni minuti, errore *bad request*
su `…/mossa.json`.

**Diagnosi (verificata sul DB):** nella posizione di sessione 13 il Bianco (umano) era **sotto
scacco** con **3 sole mosse legali** (`d1e2`, `f1e2`, `f3e5`); il motore era corretto. Il 400
"Mossa non valida" derivava da un **disallineamento client↔server**: la mossa inviata non era
più legale nello stato reale. Causa a monte: la **classe dell'IA remota** (`_qwen_move`).

**Difetti corretti:**
1. **`backend/app/ai.py` (`_qwen_move`)**: confrontava un intero con mosse che per scacchi/dama
   sono tuple/percorsi → non combaciava **mai** → ad ogni mossa IA faceva una chiamata HTTP
   (fino a 20s) e poi ripiegava sul locale (rallentamento "dopo alcuni minuti"). Ora il match
   avviene per **id mossa** (estratto `_match_move`, valido per tutti i giochi) e restituisce
   l'oggetto-mossa; timeout ridotto e configurabile (`QWEN_TIMEOUT`, default 10s).
2. **Frontend (`play.html`)**: in caso di errore di una mossa il client faceva *revert* allo
   stato pre-mossa, ma il server poteva aver già applicato la mossa → disallineamento permanente.
   Ora il client si **risincronizza** con lo stato reale (nuovo endpoint `…/stato.json`,
   `play_state_json`) invece di indovinare.

**Test:** aggiunti test di `_match_move` (scacchi/tris/dama) senza rete. **62 test** verdi; lint
pulito. Verificato dal vivo: `stato.json` 200; mossa legale ok; mossa illegale → 400 JSON
(gestito dal risync).

---

## 2026-06-28 — Quarto gioco: Scacchi (con libro di aperture)

**Obiettivo:** integrare gli **scacchi** completi e gestire le **tecniche di apertura**.

**Realizzato:**
- **Motore** (`engine/games/chess.py`): regole complete — generazione mosse legali con
  filtro di scacco, **arrocco**, **en passant**, **promozione**, **scacco matto/stallo**,
  **regola 50 mosse**, **materiale insufficiente**. Euristica materiale + centralità.
  Correttezza verificata con **perft** (20 / 400 / 8902 esatti) + test su matto del barbiere,
  stallo, promozioni.
- **Aperture** (`engine/games/openings.py`): libro in notazione UCI (Italiana, Siciliana,
  Scozzese, Spagnola, Francese, Caro-Kann, Petroff, Inglese, Gambetto di Donna, Est-Indiana,
  Nimzo, …). `detect_opening` riconosce l'apertura in corso; `book_move` propone una
  continuazione di libro. L'IA, in apertura, **gioca le linee di libro** (sorgente "book"),
  poi passa a Qwen/minimax.
- **IA**: aggiunta la **potatura alpha-beta** alla ricerca locale (necessaria per gli scacchi;
  giova a tutti i giochi). `choose_move` ora accetta lo `history` (id mosse) per il libro.
- **Backend**: il log delle mosse registra anche l'**id** (UCI); la vista sessione espone il
  nome dell'**apertura** corrente; l'IA riceve lo storico per il libro (anche nel batch).
- **Frontend**: la scacchiera "a selezione" ora copre anche gli scacchi (board 8×8 a colori,
  selezione origine→destinazione, **scelta di promozione**, arrocco/en passant gestiti via le
  `changes` della mossa); il nome dell'apertura è mostrato in pagina. Vista dama riallineata a
  `changes`.
- **Test**: motore scacchi (perft, matto, stallo, promozioni, aperture) + sessione scacchi
  (basi, apertura riconosciuta, IA da libro); aggiornati i test esistenti. **58 test** verdi;
  lint `ruff` pulito.

**Verifiche dal vivo:** sessione scacchi (64 celle, 20 mosse iniziali); `e2e4` → l'IA risponde
da libro (`d7d6`, "Difesa Pirc"); `/games` segna chess `playable`; frontend con Scacchi nel
selettore e scacchiera resa.

**Semplificazione nota (scacchi):** non è gestita la **patta per ripetizione** (richiede lo
storico nello stato); gestiti stallo, matto, 50 mosse e materiale insufficiente.

---

## 2026-06-28 — Terzo gioco: Dama italiana

**Obiettivo:** integrare la **Dama italiana** giocabile (umano/IA).

**Realizzato:**
- **Motore**: `engine/games/draughts.py` (8×8 su caselle scure, 12 pedine/parte). Regole:
  pedine muovono/catturano solo in avanti; **dama** corto raggio in tutte le diagonali;
  **cattura obbligatoria** col **massimo numero di prese**; **una pedina non cattura una dama**;
  promozione a dama sull'ultima traversa (termina la mossa). Euristica (materiale + avanzamento)
  per l'IA a profondità limitata. Registrato come `checkers`.
- **Codifica mosse generica**: l'interfaccia `Game` ora ha `move_id`, `view_board`,
  `legal_moves_view`; una mossa è identificata da una **stringa id** (cella, colonna o percorso
  `35-21`). Il backend valida la mossa per id; `MoveIn.cell:int` → `MoveIn.move:str`. La vista
  sessione espone `board` (via `view_board`, simboli ⛀⛁⛂⛃ per la dama) e `playable_moves`
  (lista strutturata from/to/captures/symbol) per i giochi a selezione.
- **Frontend**: scacchiera generica estesa al tipo **draughts** (selezione origine→destinazione,
  evidenziazione mosse, catture, dame), oltre a clic-cella (Tris) e colonna (Forza 4); il JS
  invia l'**id mossa**. Setup con la Dama nel selettore.
- **Test**: motore dama (cattura obbligatoria, massimo prese, pedina-non-cattura-dama,
  promozione), sessione dama (basi + mossa, vs IA); aggiornati i test esistenti alla nuova
  codifica `move`. Totale **50 test** verdi; lint `ruff` pulito.

**Verifiche dal vivo:** sessione dama 8×8 (64 celle, 7 mosse d'apertura); mossa umana a3-b4 →
risposta IA d6-c5; frontend con Dama nel selettore e scacchiera resa.

**Semplificazioni note (dama):** non sono ancora applicate le priorità FID fini tra catture di
pari numero (preferire la dama, catturare più dame, prima le dame) né le patte per ripetizione.

---

## 2026-06-28 — Secondo gioco: Forza 4 (scacchiera generica)

**Obiettivo:** integrare **Forza 4** come gioco giocabile (umano/IA/batch).

**Realizzato:**
- **Motore**: `engine/games/connect4.py` (griglia 7×6, mossa = colonna con caduta, vittoria a 4
  in orizzontale/verticale/diagonale, serializzazione, notazione colonna 1-based, **euristica**
  per finestre di 4 + controllo del centro); registrato in `registry`. Interfaccia `Game`
  estesa con `rows`/`cols`/`move_type`, `heuristic` e `search_depth`.
- **IA**: la ricerca locale è ora **minimax completo** per i giochi piccoli (Tris,
  `search_depth=None`) e **a profondità limitata con euristica** per i grandi (Forza 4,
  `search_depth=4`) — altrimenti il minimax completo sarebbe intrattabile. Prompt Qwen reso
  generico (vale per qualsiasi gioco).
- **Backend**: la vista sessione espone `rows`/`cols`/`move_type`/`game_name`; `/games` ora
  indica `playable` (true solo per i giochi implementati nel motore).
- **Frontend**: scacchiera **generica** in `play.html` (JS) che gestisce sia il clic sulla
  casella (Tris) sia la **caduta in colonna** (Forza 4), con animazione e ritardo IA; setup
  partita con **selettore del gioco** (solo giochi giocabili). Form `TrisSetupForm` →
  `GameSetupForm`.
- **Test**: motore Forza 4 (drop, vittoria verticale, colonna piena, notazione), sessione
  Forza 4 umano-vs-umano (vittoria) e umano-vs-IA (risposta), flag `playable`. Totale **42
  test** verdi; lint `ruff` pulito.

**Verifiche dal vivo:** `/games` con `playable` corretto; sessione Forza 4 6×7 a colonne; mossa
umana → risposta IA (euristica locale); setup con selettore Tris/Forza 4; play page che rende
la scacchiera generica.

---

## 2026-06-28 — Parametri di programma + interfaccia super admin

**Obiettivo:** rendere tutto il programma parametrizzabile e gestire ogni parametro da
un'interfaccia di super admin.

**Realizzato:**
- **Backend**: registro centrale dei parametri in `settings_service.py` (categorie: Generale,
  Utenti, Punteggio, Gruppi, IA, Giochi; tipo, default, etichetta) + tabella `settings`;
  `seed_settings` allo startup. Router `admin` (`GET /admin/settings` aperto in lettura,
  `PUT /admin/settings` protetto da header `X-Admin-Token` == env `ADMIN_TOKEN`) e router
  `config` (`GET /config` pubblico per il frontend).
- **Parametri collegati al comportamento**: punteggi vittoria/patta/sconfitta (`services`),
  voti minimi per fondare un gruppo (`groups`), abilitazione registrazione utenti (`users`),
  ritardo mossa IA (frontend), numero massimo partite batch (`sessions`).
- **Frontend**: pagina **super admin** (`/admin/`) che mostra i parametri raggruppati per
  categoria con input per tipo (sì/no, numero, testo) e richiede il token per salvare; voce
  di menu «Admin». Il ritardo IA della pagina di gioco ora arriva da `/config`.
- **Config**: `ADMIN_TOKEN` in `.env.example`; nei test impostato a `test-admin` (conftest).
- **Test**: parametri seedati/elencati, `/config`, token obbligatorio per la modifica, chiave
  sconosciuta → 400, punteggio configurabile (vittoria a 5 → score 5), registrazione
  disattivabile (403). Totale **33 test** verdi; lint `ruff` pulito.

**Verifiche dal vivo:** `/admin/` rende il form; `PUT` senza token → 401; modifica con token via
CSRF → `ai.move_delay_ms` 700→1500 effettivo subito su `/config`.

**Estendibilità:** aggiungere un parametro = una voce in `SETTINGS_DEFS` + leggerlo con
`settings_service.get(...)` dove serve; comparirà da solo nell'interfaccia super admin.

---

## 2026-06-28 — Nota: falso allarme `OperationalError` (moves_json)

Durante una prova è comparso:
`sqlite3.OperationalError: table game_sessions has no column named moves_json`.

**Causa: errore d'uso, non un bug del codice.** Il backend era stato avviato puntando a un
database SQLite **obsoleto/diverso**. Il default `DATABASE_URL = sqlite:///./scacchi.db` è
**relativo alla cartella di avvio**: lanciando il backend da una directory diversa si usa/crea
un altro file, privo della colonna `moves_json` aggiunta nello step precedente. Il
`backend/scacchi.db` corretto contiene già la colonna (verificato: 1 utente, 2 partite).

**Nessuna modifica al codice.** Come evitarlo: avviare il backend dalla cartella `backend/`
(come fa `make backend`) oppure impostare un `DATABASE_URL` con **percorso assoluto**; un DB
obsoleto creato per sbaglio si può eliminare (sono solo dati di sviluppo).

*Miglioramento futuro:* introdurre **Alembic** per le migrazioni, così i cambi di schema non
richiederanno più di ricreare il DB in sviluppo.

---

## 2026-06-28 — Log mosse, animazione/ritardo IA e storico partite

**Obiettivo:** mostrare la mossa dell'IA con un piccolo ritardo e un'animazione; aggiungere
un widget con il log delle mosse; salvare il log nello storico di entrambi i giocatori.

**Realizzato:**
- **Motore**: `Game.describe_move` (notazione mossa) + implementazione Tris (es. cella 4 → `b2`).
- **Backend**: nuova colonna `GameSession.moves_json` (log mosse); le mosse (umane e IA) sono
  registrate in creazione/mossa/auto-IA; il `_view` espone `moves`. Nuovo endpoint
  `GET /users/{id}/history` con le partite concluse (esito dal punto di vista del giocatore,
  avversario, log mosse) — la stessa partita compare nello storico di **entrambi** i giocatori.
- **Frontend**: pagina di gioco riscritta con **widget del log mosse** e **JS** che mostra
  subito la mossa dell'umano e poi rivela la mossa dell'IA dopo un **ritardo (~700ms)** con
  animazione `pop` e indicatore «L'IA sta pensando». Endpoint JSON same-origin
  `…/mossa.json` per il JS (CSRF via header); il form resta come fallback senza JS. La scheda
  giocatore mostra lo **«Storico partite»** con log mosse espandibile.
- **Test**: notazione mosse, registrazione del log nella sessione, storico per-utente (esito
  vittoria/sconfitta dai due lati). Totale **27 test** verdi; lint `ruff` pulito.

**⚠️ Cambio schema DB:** aggiunta `moves_json` a `game_sessions`. Senza migrazioni (Alembic non
ancora introdotto), per lo sviluppo va **eliminato il DB** esistente per ricrearlo:
`rm backend/scacchi.db` prima di riavviare il backend.

---

## 2026-06-28 — IA-vs-IA: N partite consecutive

**Obiettivo:** quando entrambi i giocatori sono IA, permettere di giocare N partite
consecutive (es. 100) e vedere il riepilogo.

**Realizzato:**
- **Backend**: endpoint `POST /sessions/batch` ({game_code, count 1..1000}) che simula N
  partite IA-vs-IA in memoria (nessuna persistenza, nessun punteggio) e restituisce il
  riepilogo (vittorie X/O, patte). Schema `BatchCreate` con validazione di `count`.
- **IA**: il minimax locale ora sceglie **a caso tra le mosse ugualmente ottimali** → le
  partite consecutive variano pur restando a gioco perfetto (a Tris quindi sempre patte).
- **Frontend**: nuovo campo «Partite consecutive» nel setup (usato solo se entrambi i lati
  sono IA e count > 1); pagina di riepilogo `batch_result.html`.
- **Test**: aggiunti test del batch (riepilogo coerente; validazione count 0/1001 → 422).
  Totale **24 test** verdi; lint `ruff` pulito.

**Nota:** con Qwen configurato un batch numeroso comporta molte chiamate API (più lento).

---

## 2026-06-28 — Tris giocabile (umano e IA via Qwen)

**Obiettivo della sessione:** primo gioco realmente giocabile, il **Tris**, con possibilità di
giocare tra umani e contro un'IA collegata a **Qwen**.

**Realizzato:**
- **Motore** (`engine/`): gioco concreto `TicTacToe` (stato immutabile, mosse legali,
  vittoria/patta, serializzazione, rendering testuale); registro dei giochi (`registry.py`);
  estesa l'interfaccia `Game` con `serialize_state`/`deserialize_state`/`render_text`.
- **Backend** (`backend/app/`): modello `GameSession` (stato persistito, lati umano/IA),
  router `sessions` (crea partita, mossa, lettura), modulo `ai.py` (Qwen via DashScope
  OpenAI-compatible + **fallback minimax locale ottimale**), modulo `services.py` con la
  logica punti condivisa (refactor di `matches.py`). A fine partita i punteggi dei giocatori
  umani si aggiornano automaticamente.
- **Frontend** (`frontend/`): pagina di setup partita (X/O = umano o IA), scacchiera Tris
  cliccabile, gestione turni e messaggi (incl. «L'IA ha giocato…»); voce di menu «Gioca».
- **Config**: variabili `QWEN_API_KEY` / `QWEN_BASE_URL` / `QWEN_MODEL` in `.env.example`;
  `httpx` aggiunto alle dipendenze backend.

**Prassi PEP8 + test + commit (richiesta dall'utente):**
- Aggiunta suite **pytest** (`pyproject.toml` con `pythonpath`/`testpaths`) + `ruff` (PEP8) +
  `requirements-dev.txt`. **22 test** verdi (engine, API backend, sessioni, smoke frontend).
- Lint `ruff` pulito; codice formattato.

**Verifiche dal vivo:** AI-vs-AI → patta (minimax); flusso umano-vs-IA dal frontend con CSRF
(creazione partita, mossa umana, risposta IA, banner «L'IA ha giocato», turno che torna
all'umano); backend `/sessions/{id}` coerente.

**Note tecniche:** l'IA usa Qwen se `QWEN_API_KEY` è impostata, altrimenti il minimax locale
(così il gioco è sempre giocabile). Aggiunto un piccolo hack di `sys.path` in
`backend/app/__init__.py` per importare il pacchetto `engine` dalla root a prescindere dalla
cartella di avvio.

**Prossimi passi:** autenticazione; gioco a distanza in tempo reale; Forza 4 / Dama / Scacchi;
rating Elo; regole di gestione dei gruppi.

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
