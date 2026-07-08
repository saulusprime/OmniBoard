# HANDOFF — Storico delle sessioni di lavoro

> Registro cronologico di tutte le sessioni e delle operazioni compiute.
> **La voce più recente è in cima.** Ogni voce descrive contesto, decisioni e modifiche.

---

## 2026-07-08 — Promozione con dialog grafico

**Richiesta (utente):** promozione con dialog grafico (al posto di
`window.prompt`).

- `choosePromotion` è ora una **Promise**: overlay sulla griglia
  (`.promo-overlay`, z-index sopra flyer e ghost) con pannello di quattro
  bottoni ♛♜♝♞ — classe `.cell csq-l` + lato al tratto, così i COLORI DEL TEMA
  arrivano dalle regole esistenti (`.t-… .cell.x/.o`) senza CSS nuovo per i
  pezzi. Click fuori dal pannello o Esc = ANNULLA (la mossa non parte, il pezzo
  resta selezionato→deselezionato); tasti q/r/b/n scelgono da tastiera.
- Chiamanti adeguati al flusso asincrono con `resolvePromotion(opts)`: click
  (`onSelect`) e drag&drop (pointerup).
- **Guardia dama**: più mosse sulla stessa destinazione nella dama sono
  PERCORSI DI PRESA equivalenti (già filtrati dalle priorità FID), non
  promozioni → si gioca il primo come da sempre (senza la guardia il dialog
  sarebbe comparso VUOTO: i suffissi q/r/b/n non esistono negli id della dama).
- L'overlay vive dentro la griglia: `renderCells` tocca solo `children[0..63]`
  (come i flyer), quindi un eventuale ridisegno non lo distrugge.

**Verifiche:** node --check, manage.py check, 241 test verdi (solo frontend).

---

## 2026-07-07 — Scacchiera migliore: drag&drop, ultima mossa, rotazione, catture

**Richiesta (utente):** drag&drop, evidenzia ultima mossa, orientamento dal lato
del Nero, coordinate, pezzi catturati a lato. (Solo frontend.)

**Scelta architetturale — l'orientamento ruota solo la CSS `order`**: il DOM
della griglia resta in ordine di scacchiera (0..63), a cambiare è la POSIZIONE
delle celle nella grid. Così TUTTO il codice indicizzato esistente (flyer,
badge, syncCell, hint, cellRect via getBoundingClientRect) funziona invariato
nelle due viste. Auto-flip per il Nero remoto (MY_SIDE=="o", scacchi e dama) +
pulsante «🔄 Ruota»; il flip ricrea griglia e cornice (`frameBoard` ha ora il
parametro `flipped`: coordinate A–H/1–8 che seguono la vista).

- **Drag&drop** (pointer events, scacchi e dama): pointerdown su un proprio
  pezzo seleziona e mostra le destinazioni; oltre 6px parte il ghost
  (`.dragghost`, colori per tema come i flyer; sorgente attenuata). Al rilascio:
  `elementFromPoint` → `dataset.bi` della cella → stessa via di `onSelect`
  (promozione compresa); rilascio sulla casella di partenza = resta selezionato;
  fuori bersaglio = deselezione. Il click sintetico post-drop è SOPPRESSO
  (flag consumato da onSelect); tap semplice = flusso classico intatto.
  `touch-action:none` sulle celle incorniciate (niente scroll col dito).
- **Ultima mossa evidenziata**: `.lastmv` (velo dorato in inset shadow, sotto la
  selezione); `lastMoveSquares()` — in partita l'ultima del log, in MOVIOLA la
  semimossa corrente (replayAt); scacchi = origine+destinazione dall'id uci,
  dama = l'intero percorso ("42-33-19").
- **Pezzi catturati** (`renderCaptured`, aggiornato da renderCells): confronto
  col corredo standard — scacchi per tipo con `Math.max(0,…)` anti-promozione e
  **bilancio materiale** (+n a chi è avanti); dama conteggio pedine; NASCOSTO
  nelle partite da FEN (corredo non standard).

**Verifiche:** node --check sul JS (tag Django spogliati), manage.py check,
suite 241 verdi (nessun cambio backend).

---

## 2026-07-07 — Dama potenziata: priorità FID, ripetizione, motore dedicato

**Richiesta (utente):** potenziamo la dama.

**1. Priorità FID complete sulle catture** (`engine/draughts/game.py`):
`_capture_paths` ora traccia i PEZZI CATTURATI in ordine di presa; `legal_moves`
applica la cascata del regolamento tecnico FID: massimo numero di pezzi → a
parità si prende CON LA DAMA → a parità il maggior numero di dame → a parità la
linea che incontra PRIMA una dama (confronto lessicografico sulle posizioni
delle dame lungo la presa) → scelta libera. Invariata la regola «una pedina non
cattura una dama».

**2. Patta per triplice ripetizione**: `Draughts.is_repetition_draw(history)`
(chiave scacchiera+tratto, storia rigiocata; prudente su storie non
ricostruibili). `finish_if_terminal` la usa già per ogni gioco → i finali
dama-contro-dama non sono più infiniti. Possibile solo con dame in campo (le
pedine non tornano indietro).

**3. Motore dedicato** (`engine/draughts/engine.py`, NUOVO — si aggancia al
dispatch `engine_move` di `local.best_move`, al posto del minimax generico a
profondità fissa 4):

- negamax alpha-beta con **approfondimento iterativo** e budget di tempo (si
  tiene l'ultima profondità completata);
- **estensione delle catture**: a profondità 0, finché ci sono prese
  obbligatorie si continua (tetto −8) — l'orizzonte sulle prese forzate era il
  difetto principale del minimax generico;
- TT (scacchiera, tratto) a profondità preferita, SENZA flag alpha/beta
  (semplificazione dichiarata); `tt`/`stop` compatibili con la catena della
  piattaforma;
- **jitter riscalato**: la piattaforma lo esprime in centipedoni scacchistici
  (100 = un pedone), l'euristica dama vale ~3 a pedina → ×0,03 (i livelli
  Novizio/Apprendista sbagliano anche a dama, in proporzione).

**4. Euristica arricchita**: oltre a materiale (3/5) e avanzamento, **trincea**
(+0,25 alle pedine sulla propria prima traversa) e **centro** (+0,15).

**Test (+8, 241 verdi):** le tre priorità FID su posizioni costruite (dama
obbligata, più dame, dama incontrata prima), pedina-non-cattura-dama invariata,
ripetizione (2 occorrenze no / 3 sì, storia non ricostruibile mai) su istanza
con partenza ridefinita, motore: legale e rapido, non regala la presa («shot»),
domina un greedy a 1 mossa in ≤120 semimosse.

---

## 2026-07-07 — Riconoscimento del tilt + bias cognitivi misurabili

**Richiesta (utente):** il riconoscimento del tilt e i bias cognitivi.

**Tilt** (`app/tilt.py`): due segnali, tutti da dati esistenti (mai lavoro del
motore):

- **sconfitte rapide consecutive** — serie dalle ultime 10 partite concluse,
  interrotta al primo non-persa; «rapida» = ≤ `tilt.quick_plies` (40) semimosse;
  scatta a `tilt.losses` (3);
- **ACPL peggiore del solito** — serie di sconfitte + ACPL delle ultime 3
  partite ANALIZZATE > `accuracy.acpl` del profilo × `tilt.acpl_factor` (1,25).

`GET /users/{id}/tilt` → {tilted, reasons, streak, acpl, advice, last_loss_at}.
Risposta SOFT di default: banner nel setup (Django, utente loggato) con
esercizio consigliato e link alle lezioni. **Blocco forzato SOLO opzione admin**
(`tilt.block`, default false): `create_session` rifiuta (403) nuove partite di
SCACCHI per giocatori in tilt entro `tilt.block_cooldown_min` (30′) dall'ultima
sconfitta; mai sulle partite in corso, mai sugli altri giochi.

**Bias cognitivi** — implementata la parte ONESTA (pattern misurabili sullo
storico); il confronto con database GM resta ricerca (TODO aggiornato).
`chess_profile._biases` → `profile["biases"]` (lista {code,label,detail,share,
games}), soglie ≥5 partite / ≥40%:

- donna precoce (Q nelle prime 5 mosse proprie);
- re in centro (nessun O-O/O-O-O o oltre la 15ª propria, partite ≥20 semimosse);
- coazione alla cattura (≥50% dei blunder «??» dell'analisi sono catture, ≥3);
- monotonia in apertura (≥4 delle prime 8 mosse proprie con lo stesso tipo di
  pezzo; pedoni e arrocco ESCLUSI — 4 spinte di pedone sono normali).

Scheda giocatore: sezione «Bias ricorrenti».

**Test (+7, 233 verdi):** tilt scatta alla terza rapida (non alla seconda), il
vincitore non è in tilt, l'avviso resta soft (partita creabile), blocco admin
403 con «anti-tilt» nel detail (e Tris NON bloccato), la vittoria azzera la
serie; bias su sessioni finte (donna+re in centro, monotonia+catture, campione
minimo) e chiave `biases` esposta dal profilo.

---

## 2026-07-07 — «Spiegami questa mossa» (coach LLM in moviola)

**Richiesta (utente):** implementiamo «Spiegami questa mossa» (prima voce
dell'AI Coach nel TODO).

**Endpoint** `POST /sessions/{id}/explain` (solo scacchi, `ExplainIn.ply`):

- raccoglie SOLO dati già prodotti: posizione prima della mossa rigiocata col
  motore (FEN, anche da `start_fen`), valutazione/perdita/mossa preferita
  dall'analisi (se calcolata), badge di qualità del commentatore, nome
  dell'apertura, eventuale nota del giocatore;
- prompt da istruttore («spiega COSA fa la mossa e PERCHÉ, ≤3 frasi, non
  proporre di continuare la partita») al provider ATTIVO via
  `api_ai.guarded_complete` → protetto dal circuit breaker; 503 se nessun
  provider o circuito aperto, 403 se `coach.explain_enabled` (nuovo parametro)
  è spento;
- la spiegazione è SALVATA nello storico della mossa (`moves_json[ply-1]
  ["explain"]`, max 600 caratteri): il secondo clic risponde `cached: true`
  senza richiamare il modello, e il testo ricompare navigando la moviola.

**Frontend**: pulsante «🎓 Spiegami questa mossa» sotto le note della moviola
(proxy Django `partite/<id>/spiega.json`); il testo persistito si mostra da solo
quando ci si ferma su una mossa già spiegata.

**Test (+4, 226 verdi):** 503 senza provider, prompt coi dati (mover/notazione/
FEN/nota) + cache al secondo clic + persistenza nella vista, validazioni
(ply/404/solo scacchi), 403 da interruttore. Nota: il finto provider va attivato
DOPO aver giocato la partita, o il commentatore LLM (stesso scudo) cattura i
prompt.

---

## 2026-07-07 — Cache del profilo avversario

**Richiesta (utente):** cache del profilo avversari.

**Problema:** `chess_profile.build_profile` (fino a 200 sessioni + parse delle
analisi) girava a OGNI mossa dell'IA nelle partite umano-vs-IA (`opponent_style`)
e a ogni visita della scheda giocatore.

**Soluzione** (`app/profile_cache.py`): una copia per giocatore in memoria
(lock: worker IA e richieste su thread diversi), con doppia scadenza:

- **invalidazione a eventi** — il profilo cambia solo in due punti, che ora
  chiamano `invalidate(user_id)`: `services.finalize_session` (partita di
  scacchi conclusa, entrambi i giocatori umani) e `analysis._run` (analisi
  scritta → accuracy/debolezze nuove);
- **TTL di sicurezza** `profile.cache_ttl_s` (default 300s; 0 = cache
  disattivata) per ogni percorso di scrittura non previsto.

Chiamanti aggiornati: `gameplay.opponent_style` e l'endpoint
`/users/{id}/chess-profile` (stessa freschezza per l'IA e per la pagina). Il
dict restituito è CONDIVISO e va trattato come immutabile (`opponent_style` già
copia ciò che adatta).

**Test (+3, 222 verdi):** riuso (contatore su build_profile, stessa istanza),
TTL 0 = nessuna cache, integrazione «la scheda si aggiorna appena la partita
finisce» (senza invalidazione vedrebbe la copia vecchia). Adeguato
test_opening_target: il monkeypatch dello stile passa da `profile_cache.get`
(nuovo livello di aggancio) invece che da `build_profile`.

---

## 2026-07-07 — Circuit breaker dei provider + cifratura dei token

**Richiesta (utente):** circuit breaker e cifratura dei token provider.

**Circuit breaker** (`app/breaker.py`, stato in memoria per processo):

- Dopo N errori CONSECUTIVI (default 3) il circuito del provider si APRE: le
  chiamate remote si saltano per il raffreddamento (default 120s) — la partita
  usa subito il giocatore locale senza pagare il timeout a ogni mossa. Scaduto
  il raffreddamento è MEZZO APERTO: la prima chiamata fa da sonda (successo →
  chiuso e conteggio azzerato; errore → riaperto).
- Scudo unico `api_ai.guarded_complete` usato da `remote_move` E dal
  commentatore LLM; una risposta di rete qualsiasi (anche non interpretabile) è
  un successo. `ping` («Verifica connessione») BYPASSA il breaker e ne registra
  l'esito: sonda manuale.
- Soglie nei parametri `providers.breaker_failures`/`providers.breaker_cooldown_s`,
  iniettate nella cfg del provider da `ai_providers.get_config` (api_ai non ha il
  DB). **Bug trovato dal test**: `or` sul cooldown mangiava lo 0 legittimo
  (riprova subito) → sostituito con check su None.
- Stato esposto in `list_providers` (`breaker: {open, failures, retry_in_s}`) e
  badge «⛔ sospeso ~Ns» nella pagina Provider IA.

**Cifratura dei token a riposo** (`app/token_crypto.py`, dipendenza NUOVA
`cryptography` — Apache-2.0/BSD, ok col progetto MIT):

- Fernet; formato `enc:<token>` nella STESSA colonna `ai_providers.api_key`
  (nessuna migrazione di schema). Righe legacy in chiaro cifrate al primo avvio
  (`seed_providers`); token da env cifrati alla nascita.
- Chiave: `TOKENS_KEY` in `.env` (Fernet.generate_key(), consigliata in
  produzione) o DERIVATA da `ADMIN_TOKEN` (PBKDF2-SHA256, 200k, sale
  applicativo) per lo zero-config in sviluppo. Chiave cambiata → decrypt None
  (mai eccezioni): config assente (ripiego locale), `key_unreadable: true` in
  lista, badge «da reinserire» e messaggio dedicato in «Verifica connessione».

**Test (+6, 219 verdi):** round-trip/legacy/chiave-cambiata, PUT admin che salva
cifrato e config che decifra (con soglie breaker incluse), migrazione lazy del
seed, flag token illeggibile, breaker apre/half-open/richiude, scudo che salta
le chiamate a circuito aperto (contatore) e sonda che richiude. Pulizia dei
token di prova a fine test (ordine casuale della suite).

---

## 2026-07-07 — Scacchiera da torneo (cornice + coordinate)

**Richiesta (utente):** una scacchiera migliore (riferimento: temi/scacchiera.jpg,
scacchiera in legno da torneo).

**Implementazione (solo frontend):**

- `board_css.html`: CSS della cornice (`.bframe` inline-grid 3×3: bande da 26px
  sui quattro lati, venatura leggera con repeating-linear-gradient, ombra di
  profondità, FILETTO d'intarsio con outline+offset attorno alle case) e helper
  JS condiviso `frameBoard(grid, moveType, rows, cols, cellPx, theme)` che
  avvolge la griglia: coordinate A–H/1–8 sui quattro lati per gli SCACCHI (vista
  sempre col Bianco in basso: nessun flip da gestire), sola cornice per la DAMA,
  griglia intatta per gli altri giochi.
- Dentro la cornice le case sono A FILO (gap 0, niente bordi né angoli tondi);
  selezione e hover passano a ombre INTERNE per non sconfinare nelle case
  adiacenti. Badge di qualità e pezzi "volanti" non toccati (vivono dentro
  celle/griglia).
- Colori della cornice per TEMA via variabili CSS (--bframe/--binlay/--bcoord):
  classico, legno (mogano come il riferimento), smeraldo, ghiaccio; contrasto
  coordinate/cornice verificato ≥4.5:1 (WCAG 2.1).
- `play.html` e `learn_lesson.html` avvolgono la griglia con `frameBoard` (nelle
  lezioni le coordinate aiutano a seguire i passi: «il pedone va in e4»).

**Verifiche:** node --check sul JS dell'helper, `manage.py check`, suite completa
213 verdi (nessun cambio backend).

---

## 2026-07-07 — Classifica delle IA e tornei (Arena IA)

**Richiesta (utente):** classifica delle IA e tornei.

**Identità** (`app/ai_arena.py`): ogni configurazione di lato non umano è un
concorrente — `motore:<livello>`, `stockfish:<preset>`, `ai:<provider>`, più i
generici `ai`/`stockfish`; `identity_of` ↔ `side_columns` sono inversi (test su
tutto il catalogo).

**Rating Elo per (gioco, identità)** — tabella `ai_ratings` (**migrazione 0008**),
partenza 1500, K=32, aggiornato in `services.finalize_session` (punto unico di
fine partita) SOLO per partite IA-vs-IA con identità diverse; contro gli umani
restano i punti 3/1/0 (non c'è un rating umano da confrontare — arriverà con
l'Elo dei giocatori).

**Tornei** — tabelle `tournaments`/`tournament_games`: girone all'italiana tra
2-8 identità (singolo: una partita per coppia, X al primo elencato; doppio:
andata e ritorno). Il runner (thread; SINCRONO nei test con AI_ASYNC=0) gioca le
partite UNA ALLA VOLTA come **vere sessioni** (`advance_ai` chiamato direttamente,
non `schedule_ai`): restano nello storico con moviola/analisi/PGN e alimentano
l'Elo dal flusso normale. Una partita rotta non ferma il girone; alla ripresa le
partite già giocate si saltano. Classifica del girone coi punti di piattaforma
(`scoring.points_*`).

**API** `/arena/*`: `identities`, `ranking/{game}`, `tournaments` (POST con
validazioni 2-8/identità note/dedup, GET lista e dettaglio). Dopo lo start
sincrono il router fa `db.expire_all()` (il runner usa un'ALTRA sessione DB).

**Frontend**: pagina «Arena IA» in nav — classifica per gioco (selettore),
elenco tornei, form di creazione (checkbox dei concorrenti); pagina di dettaglio
con classifica del girone e partite (link alla sessione), in auto-aggiornamento
via polling finché il torneo è in corso.

**Test (+5, 213 verdi):** catalogo/inversi, Elo atteso + accoppiamenti,
validazioni, torneo completo sincrono (Tris, doppio girone: sessioni vere,
classifiche, conservazione dell'Elo — asserzioni a DELTA perché la classifica è
condivisa con le altre partite IA-vs-IA della suite), partite con umani che non
toccano l'Elo. Fix: mossa del Tris come stringa nel test.

---

## 2026-07-07 — Export PGN e import FEN dall'interfaccia

**Richiesta (utente):** Export PGN / import FEN dall'interfaccia.

**Export PGN** — `GET /sessions/{id}/pgn` (solo scacchi, allegato `partita-N.pgn`):
tag standard (`Event` dal nome del sito, `White`/`Black` da alias o etichetta del
lato IA, `Result` dal vincitore), mosse in **SAN** e note dei giocatori come
commenti `{…}`. Il motore ha ora lo SCRITTORE SAN (`engine/chess/pgn.py`):
`uci_to_san` (disambiguazione minima file→traversa→entrambe, arrocco, en passant,
promozione, `+`/`#` dallo stato successivo) e `san_line` (dalla posizione standard
o da FEN; si ferma al primo storico non ricostruibile — mai un movetext corrotto).
Round-trip garantito col parser esistente (`san_to_uci`). Pulsante «📄 Esporta
PGN» in partita accanto alla GIF.

**Import FEN** — campo «Posizione iniziale FEN» al setup (solo scacchi): colonna
`game_sessions.start_fen` (**migrazione 0007**), validazione col motore (due re,
lato senza tratto non in scacco, posizione non conclusa), FEN **normalizzata** con
`to_fen` prima del salvataggio. X resta il Bianco: col tratto al Nero la prima
mossa spetta a O. Tutto il mondo post-mossa riparte dalla FEN:

- `_replay_boards` (moviola/GIF) e l'export PGN (tag `SetUp`/`FEN`, numerazione
  `1...`);
- **analisi** e **commento**: posizioni UCI via nuovo helper unico
  `stockfish.uci_position(history, start_fen)` e parità delle semimosse dal
  tratto iniziale (il Nero può muovere per primo); l'analisi valuta anche la
  posizione di partenza (non è ≈ 0 come la standard);
- **Stockfish avversario**: `choose_move`/`stockfish.best_move` ricevono
  `start_fen` (mai più `startpos + moves` fuori posto);
- **ripetizione**: `is_repetition_draw(history, start_fen=…)` nel motore;
  l'anti-ripetizione della ricerca resta prudente (set vuoto se lo storico non
  riproduce lo stato — comportamento già esistente).

**Test (+11, 208 verdi):** scrittore SAN (matto del barbiere, arrocco, en passant,
promozione con scacco, disambiguazioni file/traversa, round-trip col parser,
prefisso valido da FEN), PGN completo con nota `{…}`, PGN solo-scacchi 400,
creazione da FEN + replay a 3 pezzi, validazioni FEN (malformata/re mancante/
scacco illegale/gioco sbagliato), PGN da FEN col Nero al tratto (`1... Qh1+`),
helper `uci_position`.

---

## 2026-07-07 — Livelli di difficoltà del motore locale

**Richiesta (utente):** i livelli di difficoltà.

**Design:** cinque preset del MOTORE LOCALE (`opponents/local.py::ENGINE_LEVELS`) —
Maestro (piena forza, tempo globale), Esperto (1,2 s), Medio (0,5 s), Apprendista
(0,2 s), Novizio (0,1 s) — con **jitter crescente** (0→300 cp: a jitter alto il
motore sceglie anche mosse lontane dalla migliore, cioè sbaglia in modo "umano").
Un livello scelto **scavalca il provider remoto** («Novizio» non è Claude a piena
forza). Riusa la colonna `*_ai_level` dei preset Stockfish: **nessuna migrazione**,
il tipo del lato distingue la semantica.

**Implementazione:**

- `gameplay.engine_level_params(session, player, default_think)` →
  `(think_ms, jitter, usa_provider)`; `advance_ai` la usa al posto dei valori fissi
  (jitter storico 15 per i lati senza livello) e passa `provider=None` se il livello
  è attivo. Il tetto dell'orologio (`tc_category`) continua ad applicarsi.
- Validazione al setup: livello sconosciuto → 400; livello+provider insieme → 400.
- Vista: `level_label` risolta da preset Stockfish O livello motore; intestazione di
  `play.html` mostra «IA — Novizio (per imparare)».
- Form Django: voci «Motore — …» (`motore:<livello>`) tra le IA e Stockfish.
- **Pondering**: i livelli sotto «maestro» sono esclusi (la TT ponderata a piena
  forza rinforzerebbe un livello depotenziato).

**Test (+6, 197 verdi):** creazione con livello (201 + etichetta in vista), livello
sconosciuto 400, conflitto livello+provider 400, risoluzione parametri per lato
(incl. lato Stockfish ignorato), ordinamento dei preset, pondering che salta i
livelli deboli ma parte col Maestro.

---

## 2026-07-07 — Pondering (pensare durante il turno dell'umano)

**Richiesta (utente):** il pondering con la mossa async.

**Design:** invece del ponderhit classico (predire la replica), si pondera LA POSIZIONE:
durante il turno dell'umano un thread cerca sulla posizione corrente riempiendo una
**transposition table condivisa per sessione**; qualunque mossa l'umano scelga, la
ricerca vera del worker riparte con i sottoalberi già valutati.

**Implementazione:**

- Motore: `best_move(..., tt=None, stop=None)` — TT iniettabile e `threading.Event` di
  stop controllato in `tick()` (catena `engine_move` → `local.best_move` →
  `choose_move`, parametro `tt` fino al dispatcher).
- **`app/ponder.py`**: store per sessione {tt, stop, thread}; `start` quando il worker
  IA finisce e il turno passa all'umano (solo scacchi, un solo lato IA di tipo «ai» —
  Stockfish e provider esclusi —, `ponder.enabled`, async attivo; con AI_ASYNC=0 no-op);
  `stop` all'arrivo della mossa umana in `make_move` (la TT SOPRAVVIVE per la ricerca
  vera); `drop` a partita finita (`finish_manual`, fine del worker) libera la memoria.
  Pensata max 60 s; cap TT 400k voci (oltre: reset).
- `advance_ai` passa `tt=ponder.tt_for(session.id)` a `choose_move`.

**Test (+3, 191 verdi):** TT condivisa → seconda ricerca < ⅓ dei nodi; stop pre-armato
→ uscita < 2 s con mossa legale (depth 1 garantita); ciclo di vita completo su sessione
vera (start/active/stop con TT conservata/drop) + esclusioni via finti oggetti-sessione
(il primo test creava una partita IA-vs-IA SINCRONA: 132 s → riscritto, 1,9 s).

---

## 2026-07-07 — Finali: mop-up e riconoscimento KPK

**Richiesta (utente):** la voce TODO «Finali».

**Implementazione (in `evaluate()`):**

- **Mop-up** (attivo quando un lato ha ≥ una torre di vantaggio e l'avversario è quasi
  nudo): `8·dist_centro×2(re perdente) + 5·(14 − Manhattan fra i re)` — ogni passo del
  re perdente verso il bordo vale ±16 cp e domina il rumore posizionale: il matto
  arriva anche quando sta OLTRE l'orizzonte di ricerca.
- **KPK** (re+pedone contro re): regola del QUADRATO con il tempo (pedone imprendibile
  → ~750+), pedone di TORRE col difensore nell'angolo (→ ~20, patta da manuale), re
  difensore davanti al pedone (→ ~30), altrimenti vantaggio moderato crescente con
  l'avanzata e l'appoggio del proprio re. Lezione emersa: l'euristica deve
  **SOSTITUIRE** la valutazione accumulata (che conterebbe il pedone anche nelle
  patte), non sommarsi.
- Mini-tablebase: rimandata — non necessaria coi risultati funzionali attuali.

**Test (+3, 188 verdi):** regola del quadrato / re davanti / pedone di torre sui FEN;
mop-up (re nero all'angolo coi re vicini > re al centro); prova FUNZIONALE: self-play
KQ vs K → matto in ~14 semimosse a 0,5 s/mossa, stabile su 3 esecuzioni (prima
versione a 0,3 s e pesi 6/4 rimescolava: pesi alzati e budget realistico). Benchmark
di regressione: nodi IDENTICI fuori dai finali.

---

## 2026-07-07 — Potenziamenti di ricerca del motore (SEE, PVS, aspiration, futility)

**Richiesta (utente):** la voce TODO «Potenziamenti di ricerca».

**Implementazione (`engine/chess/engine.py`):**

- **SEE** (Static Exchange Evaluation): swap algorithm con attaccante di minor valore,
  RAGGI X naturali (i raggi si riscandiscono dopo ogni rimozione), guardia del re (non
  ricattura su casa ancora difesa), passaggio all'indietro con lo stop facoltativo.
  In quiescence le catture con SEE < 0 vengono potate (en passant e promozioni escluse:
  restano al delta pruning).
- **PVS**: prima mossa a finestra piena, le successive sondate a finestra nulla e
  ri-cercate solo se promettono — composto con la LMR (riduzione+finestra nulla → se
  promette, prima verifica a profondità piena a finestra nulla, poi ricerca esatta).
  Applicato anche alla radice.
- **Aspiration windows**: dal terzo livello dell'iterative deepening finestra ±50 cp
  attorno al punteggio precedente; fail low/high → ricerca piena. Compatibile col
  jitter: le mosse uscite a fail-low restano fuori dall'insieme quasi-ottimale.
- **Futility pruning** a depth 1: statico+150 ≤ alpha → le mosse quiete che non danno
  scacco si saltano (mai la prima legale: matto/stallo e mossa di riserva salvi).

**Misure (profondità 6 fissa, jitter 0):** iniziale 1,48→0,95 s (23k→19k nodi),
mediogioco 5,09→1,92 s (59k→27k), tattica 8,26→2,90 s (92k→37k) — **stesse mosse e
identici punteggi** (PVS/aspiration esatte a fine ricerca). A parità di tempo il
motore guadagna ~1 livello di profondità nel mediogioco.

**Test (+3, 185 verdi):** SEE su scambi noti (DxP difeso −800, TxD +900, CxP con
torre −220, +100 coi raggi X della donna), matto del corridoio trovato, donna
minacciata che si mette in salvo senza catturare il pedone difeso (premessa del primo
tentativo di test corretta: d5 non attacca d4).

---

## 2026-07-07 — Bandierina fedele all'art. 6.9 (matti d'aiuto)

**Richiesta (utente):** patta alla bandierina se l'avversario non può dare matto con
alcuna serie di mosse (prima: solo re nudo).

**Implementazione:** `Chess.cannot_mate(board, color)` — teoria dei MATTI D'AIUTO su
base materiale (l'altro giocatore collabora, i pedoni promuovono). Il matto è
impossibile SOLO in tre casi: re nudo; re+UN cavallo contro re nudo (qualunque pezzo o
pedone avversario fa da blocco → matto d'aiuto possibile); soli alfieri di ENTRAMBE le
parti su case della stessa tinta. Re+2 cavalli PUÒ dare matto (blocco d'aiuto) →
vince a tempo. `gameplay._winner_on_time` usa il metodo del motore quando esiste
(ripiego re-nudo per giochi futuri senza) → la regola vale per la BANDIERINA e per
l'**abbandono** (che la riusa). Semantica allineata a quella di lichess
(«timeout vs insufficient material»).

**Test (+2, 182 verdi):** casistica completa di `cannot_mate` (re nudo, K+N vs nudo /
vs torre / vs pedone, K+2C, alfieri mono/bi-tinta, per lato) e `_winner_on_time` su
stati costruiti (K+N vs re nudo → patta; con torre avversaria → vittoria). MANUAL:
riga della tabella di conformità aggiornata, semplificazione rimossa dall'elenco.

---

## 2026-07-07 — Abbandono e patta d'accordo (le lacune dell'audit FIDE)

**Richiesta (utente):** implementare abbandono (FIDE 5.1.2) e patta d'accordo (9.1).

**Backend:** colonna `game_sessions.draw_offer` (**migrazione 0006**: lato con offerta
pendente). `POST /sessions/{id}/resign` {side}: vince l'avversario, MA col re nudo →
patta (riusa `_winner_on_time`, coerente con la bandierina); `finish_reason="resign"`.
`POST /sessions/{id}/draw` {side, action}: offer/accept/decline — l'offerta resta
pendente finché l'altro non risponde; la MOSSA dell'altro la rifiuta (in `make_move`);
offerta incrociata = accettazione; contro l'IA 409 («l'IA non tratta»);
`finish_reason="agreement"`. Validazione `_acting_human`: lato x/o umano, nei remote
il token deve possedere il lato (stesse regole di fiducia delle mosse). Helper
`gameplay.finish_manual` (esito+punti+spegnimento offerta). **Guardia anti-corsa**:
l'abbandono può arrivare DURANTE la pensata dell'IA → `db.refresh(session)` nel loop
del worker prima di ogni mossa.

**Frontend:** pulsanti «🏳️ Abbandona» (confirm) e «½ Offri patta» accanto all'hint;
banner «Ti è stata offerta la patta» con Accetta/Rifiuta; visibilità: solo lato umano
identificabile (hotseat = giocatore al tratto, remote = MY_SIDE), patta solo fra due
umani; esiti «(per abbandono)» / «(patta d'accordo)»; `draw_offer` in vista (i remoti
la vedono col polling).

**Test (+3, 180 verdi):** abbandono (vittoria avversario, 409 post-fine, 400 lato
IA/inesistente), flusso patta completo (accept senza offerta 409, doppia offerta 409,
decline, mossa-rifiuto, accettazione → agreement), IA che non tratta, remote con
401/403/ok. **Dal vivo:** 0006 auto-applicata; offerta → accettazione →
`finished draw agreement`.

---

## 2026-07-07 — Posizione morta corretta + audit di conformità FIDE

**Richiesta (utente):** verificare la patta per scarsità di pezzi nel regolamento
ufficiale, applicare la correzione proposta, rivedere la corrispondenza complessiva al
regolamento e aggiornare tutti i documenti (resilienza all'auto-compattazione).

**Verifica sulle fonti:** FIDE Laws of Chess (handbook.fide.com, E01): l'art. 5.2.2 non
elenca materiali ma definisce la **posizione morta** (nessuno può dare matto con alcuna
serie di mosse legali); 6.9 (bandierina), 5.1.2 (abbandono), 9.6 (dichiarazioni
d'ufficio alla 5ª ripetizione / 75ª mossa).

**Correzione (`Chess._insufficient`):** il vecchio controllo ignorava proprietario e
tinta delle case — dichiarava patta **Re+Alfiere+Alfiere vs Re** (con la coppia di
alfieri il matto è FORZATO: bug che derubava una vittoria) e Re+A vs Re+A su tinte
diverse (matto d'aiuto possibile). Ora: K vs K; K+minore vs K; soli alfieri (di uno o
entrambi i lati) **tutti sulla stessa tinta**. Re+2C resta correttamente viva.
Test nuovi (`engine/tests/test_dead_position.py`, +3): coppia di alfieri, alfieri
contrapposti stessa/diversa tinta, KNN, pedone sempre vivo. (Refuso di tinta nelle case
di test trovato e corretto: 27 e 36 sono la STESSA tinta, 28 quella opposta.)

**Audit FIDE completo** (tabella in MANUAL, «Conformità al regolamento FIDE»):
conformi movimento/scacco/matto/stallo, arrocco (transito del re non attaccato, b1/b8
solo libera), en passant a scadenza, promozione a scelta, ripetizione con chiave
completa, 50 mosse con azzeramenti giusti, orologi. **Semplificazioni dichiarate**:
ripetizione e 50 mosse d'ufficio al primo raggiungimento (FIDE: su richiesta, d'ufficio
a 5ª/75ª), bandierina = patta solo con re nudo, posizioni morte non-materiali non
rilevate. **Lacune scoperte → TODO**: abbandono (5.1.2) e patta d'accordo (9.1) non
esistono ancora; bandierina fedele al 6.9 pieno.

**Documenti aggiornati** (anti-perdita alla compattazione): MANUAL (tabella conformità,
intestazione), TODO (2 voci nuove), README (roadmap scacchi consolidata), MEMORY
(milestone + intestazione), memoria persistente di progetto riallineata.

---

## 2026-07-06 — Badge di qualità delle mosse + commentatore LLM (widget)

**Richiesta (utente):** un LLM come commentatore in un widget + simbolini in alto a
destra del pezzo mosso quando la mossa è da maestro / brava / codarda / stupida, ecc.

**Backend (`app/commentary.py`):** dopo OGNI mossa di scacchi (endpoint umano e worker
IA) un lavoro best-effort in background: Stockfish (piena forza, `analysis_ms`) valuta
prima/dopo — la valutazione precedente è **memoizzata per sessione** (una ricerca nuova
per mossa) — e classifica: 🤡 blunder ≥200 cp, 😬 errore ≥100, 🐔 **codarda** (ritirata
verso la propria traversa CHE perde ≥50), 🤔 imprecisa ≥50, 🌟 **da maestro** (proprio
la mossa suggerita dal motore, perdita ≤5), ⚔️ aggressiva (cattura/scacco, <30),
👍 buona. Il badge vive in `moves_json` (`quality`). Se `commentary.llm` è acceso e un
provider IA è attivo, il modello aggiunge UNA battuta in italiano (`comment`, ≤280
caratteri) riusando `api_ai._complete`. Interruttori: `commentary.enabled`/`llm`
(categoria IA). Niente Stockfish → niente badge; niente provider → niente commento;
nessun errore raggiunge la partita.

**Client (`play.html`):** `.qbadge` assoluto in alto a destra della casella di
destinazione (ultime due semimosse, una per lato), simbolo+tooltip nel log, widget
«🎙️ Commento» (ultime 4 battute) sopra il log; dopo la propria mossa un resync
ritardato (2,5 s) raccoglie badge e commento appena pronti.

**Ritocco (feedback utente):** il badge compare SOLO sull'ultima mossa, nell'angolo
alto-destro della casa di arrivo, per ~2,5 secondi (pop di comparsa, timer di
rimozione, `badgeShownPly` evita che i ridisegni lo riportino in vita).

**Test (+2, 174 verdi):** tabella di classificazione completa; partita con finto
motore → badge presente e sincrono, nessun `comment` senza provider, interruttore
spento → mossa senza badge. **Dal vivo:** e2e4 → `👍 buona` (Stockfish 18).

---

## 2026-07-06 — Libro Polyglot (.bin) con hash Zobrist

**Richiesta (utente):** supporto al formato Polyglot.

**Implementazione (`engine/chess/polyglot.py` + `polyglot_data.py`):** tabella
**RANDOM64** (781 costanti della specifica, prese dalla documentazione del formato e
**validate contro i 9 vettori ufficiali** — arrocchi, en passant condizionale «solo se
un pedone può davvero catturare», tratto). Un vettore che fallisce ha smascherato un
errore di MEMORIA nel test (a1a2 vs a1a3 della specifica), non nel codice: i termini
differenti (torre a2/a3) individuati via XOR sulla tabella. `zobrist_key(state)` dalla
nostra ChessState (riga 0 = ottava traversa → conversione), `probe` con bisect sul file
ordinato (voci 16 byte big-endian, coda spuria tollerata, cache per percorso),
`weighted_choice` proporzionale ai pesi, arrocchi «re cattura torre» → UCI.
**Priorità**: `opening_move` consulta prima il libro interno (ha i NOMI: bersagli),
poi il Polyglot via `CHESS_POLYGLOT_BOOK`. `reset_book_cache` svuota entrambi.

**Test (+3, 172 verdi):** vettori ufficiali, probing su .bin costruito nel test
(pesi, arrocco e1h1→e1g1 giocabile via opening_move su posizione fuori dal libro
interno, posizione assente → vuoto senza errori), scelta pesata (pesi nulli inclusi).

---

## 2026-07-06 — Import del libro da PGN (parser SAN)

**Richiesta (utente):** import del libro da PGN o formato Polyglot.

**Scelta di scope (dichiarata):** implementato il **PGN** (è il formato che gli utenti
hanno: repertori e partite; si sposa col libro a linee); il **Polyglot .bin** resta in
TODO come voce separata (richiede la tabella Zobrist standard da 781 costanti).

**Implementazione (`engine/chess/pgn.py`):**

- `san_to_uci(game, state, token)` — SAN → UCI **rigiocando col motore**: si filtrano le
  mosse legali per destinazione, promozione (`=Q`), pezzo (lettera SAN dalla casa di
  partenza; stato interno a lettere P/N/…) e disambiguazione (`Nbd7`, `R1e2`); arrocchi
  `O-O`/`O-O-O` (anche `0-0`); il match deve essere UNICO, altrimenti None. Suffissi
  `+ # ! ?` ed `e.p.` ripuliti. Nessuna tabella esterna: il motore è l'autorità.
- `parse_pgn(game, text, max_plies=16)` — spezza sulle intestazioni `[Event`, pulisce
  commenti `{…}`, varianti `(…)` (annidate), NAG `$n`, numeri di mossa e risultati; una
  linea di libro per partita (prefisso valido; SAN ignota → troncamento), nome da
  `Opening`/`ECO` o `Bianco–Nero`.
- **`CHESS_BOOK_FILE` accetta ora anche un .pgn**: auto-riconoscimento per estensione o
  contenuto (`[Event`); il formato testo resta invariato. Le linee importate entrano
  nell'indice per posizione: valgono nelle trasposizioni e come aperture-bersaglio.

**Test (+3, 169 verdi):** PGN a due partite (tag, commenti, varianti, NAG, arrocco,
cattura di pedone) → linee UCI esatte con nomi `C50 Partita Italiana` e `Verdi–Neri`;
disambiguazione `Nbd2`/`Nfd2` con `Nd2` ambigua → None e spazzatura → None; libro da
.pgn seguito con `prefer` (integrazione con le aperture-bersaglio). Un bug reale
trovato dai test: il matcher usava i glifi della vista invece delle lettere dello stato.

---

## 2026-07-06 — Patta per triplice ripetizione

**Richiesta (utente):** implementare la patta per triplice ripetizione (voce TODO: il
motore la evitava in ricerca, ma la partita non terminava mai per ripetizione).

**Implementazione:** `Chess.is_repetition_draw(history)` — rigioca lo storico dalla
posizione iniziale contando le occorrenze della chiave FIDE (scacchiera, tratto, diritti
di arrocco, casa en passant: le stesse componenti dell'indice del libro); True se la
posizione CORRENTE è alla terza occorrenza. Storico non ricostruibile → nessuna
dichiarazione. Base comune: default False (giochi senza la regola).
`finish_if_terminal` ora consulta anche la ripetizione: patta d'ufficio con
`finish_reason="repetition"` (da regolamento sarebbe su richiesta; qui è automatica per
evitare partite infinite — documentato). Client: «Patta (triplice ripetizione)».

**Test (+2, 166 verdi):** giro di cavalli ×2 (2 occorrenze → False, 3 → True; base
comune sempre False); partita API che si chiude `draw/repetition` all'ottava semimossa
con 409 sulla mossa successiva. **Dal vivo:** `finished draw repetition`.

---

## 2026-07-06 — Suggerimento mossa (hint) riservato ai principianti

**Richiesta (utente):** hint per il giocatore umano; NON utilizzabile in tornei,
campionati e nelle partite tra esperti (criterio: vittorie a scacchi).

**Implementazione:** `POST /sessions/{id}/hint` — motore LOCALE a budget ridotto
(`hints.engine_ms`, default 500 ms), per tutti i giochi. Regole: 403 se disattivato
(`hints.enabled`), 403 nel **formato FIDE** (l'equivalente attuale di tornei/campionati:
erediteranno il blocco), 403 oltre `hints.max_wins` vittorie **nel gioco in corso**
(default 10 — fra due esperti nessuno può chiederlo), 409 fuori turno/partita finita,
token del giocatore al tratto nei remote. UI: pulsante «💡 Suggerimento» con notazione
e mossa evidenziata 3 s (origine/destinazione o cella). Test +3 (164 verdi: mossa
legale al principiante, 403 esperto/FIDE, interruttore admin); dal vivo: Nb1-c3.

---

## 2026-07-06 — Stima delle blunder nel profilo avversario

**Richiesta (utente):** implementare la stima delle blunder (voce TODO): quantificare
gli errori dell'avversario rianalizzando col motore il suo storico.

**Design (niente motore nel build del profilo):** `build_profile` gira a ogni mossa
dell'umano → la stima AGGREGA solo le analisi **già in cache** (`analysis_json`, le
stesse dell'analisi post-partita). Il lavoro pesante sta in
**`POST /users/{id}/analyze-history`** (`analysis.analyze_history`): accoda l'analisi
delle ultime partite non ancora analizzate (max 10, job condivisi sul lock del motore
persistente; 503 senza binario, sincrono nei test).

**Profilo:** `profile["accuracy"]` = {games_analyzed, moves, **acpl** (perdita media,
tetto 1000 cp/mossa perché i tracolli da matto non dominino), blunders, errors,
inaccuracies, blunders_per_game} calcolati sul SOLO lato del giocatore. Sotto
**20 mosse analizzate** la stima non fa testo; sopra: blunder ≥1/partita → debolezza
dichiarata + **aggressività aumentata** (+0,15·bpg, tetto 1,9), ACPL ≥120 → debolezza
«precisione bassa». Scheda giocatore: sezione «Precisione» + pulsante «🔬 Analizza lo
storico» (messaggio con le partite accodate).

**Test (+1, 161 verdi):** prima dell'analisi `accuracy` è None; analyze-history → 1
accodata (poi 0: cache), profilo con acpl 63.0 e 1 imprecisione (finto motore a cp
fisso); 503 con binario a percorso inesistente (il PATH di sviluppo ha uno Stockfish
vero), 404 utente ignoto. **Dal vivo:** il profilo di remoto_a riporta acpl 539,5 con
1 blunder (il 3.g4 del matto dell'imbecille) e 1 imprecisione (1.f3).

---

## 2026-07-06 — Apertura-bersaglio dal profilo avversario

**Richiesta (utente):** implementare le aperture-bersaglio (voce TODO): scegliere dal
libro le linee in cui l'avversario storicamente rende peggio.

**Implementazione:**

- L'indice del libro (`Chess._position_book`) ora conserva **(mossa, nome della linea)**;
  `opening_move(state, history, prefer=None)` con `prefer` filtra le continuazioni che
  appartengono alle aperture indicate — confronto per **sottostringa nei due sensi**
  («Difesa Siciliana» aggancia anche le varianti nominate). Nessun aggancio → scelta
  normale su tutto il libro (nessuna rinuncia al libro). Firma aggiornata anche nella
  base comune (`engine/common/game.py`), gli altri giochi la ignorano.
- `gameplay.opponent_style` aggiunge allo stile **`target_openings` =
  `profile["weakest_openings"]`** (le aperture con rendimento < 0,5 su ≥ N partite);
  il dispatcher (`opponents.choose_move`) le passa al libro a ogni consultazione.
  Vale per qualunque IA (motore locale, Stockfish, provider): il libro è comune.

**Test (+4, 160 verdi):** libro-mini via `CHESS_BOOK_FILE` (bersaglio deterministico,
aggancio di varianti per sottostringa, ripiego su bersaglio inesistente — il file utente
si SOMMA al libro incorporato), dispatcher con `style.target_openings`, `opponent_style`
con profilo simulato (lo stile esistente resta intatto).

---

## 2026-07-06 — Sparring, analisi post-partita, moviola con note, export GIF

**Richiesta (utente):** Stockfish come sparring; analisi post-partita; possibilità di
muoversi nel tempo di gioco (rewind/step-by-step) con note salvate nello storico;
export dell'intera partita come GIF animata.

**Backend:**

- `_PersistentEngine.evaluate()` — valutazione UCI (``score cp/mate`` + bestmove) sul
  processo persistente: la base dell'analisi.
- **`app/analysis.py`**: job in thread (sincrono con AI_ASYNC=0 nei test) che valuta
  ogni posizione (`stockfish.analysis_ms`, nuovo parametro, default 200 ms, piena
  forza) e marca gli errori — ??/?/?! a soglie 200/100/50 cp persi — con il
  suggerimento del motore (bestmove della posizione precedente); cp dal punto di
  vista del bianco, matti → ±(10000−N). Risultato in **`analysis_json`
  (migrazione 0006? no: 0005)** — calcolato una volta sola.
- **`app/sparring.py`**: match motore interno vs Stockfish a preset con Elo noto
  (colori alternati, tetto 240 semimosse); stima `diff = 400·log10(p/(1−p))` con
  clamp e margine (errore standard propagato). Un match alla volta, in background;
  `POST/GET /admin/sparring` (token admin per avviare). Zeus rifiutato (senza Elo
  simulato non c'è riferimento).
- **Moviola**: `GET /sessions/{id}/replay` — tutte le posizioni ricostruite col motore
  (apply degli id del log). **Note**: `POST /sessions/{id}/note` {ply, text} — salvate
  DENTRO `moves_json` (compaiono nello storico del giocatore); nelle partite remote
  solo i partecipanti (token), vuoto = cancella, max 500 caratteri.
- **GIF**: `GET /sessions/{id}/gif` (`app/gifexport.py`, **Pillow** nuova dipendenza) —
  un fotogramma per posizione (700 ms, ultimo 3 s, loop), scacchi con glifi Unicode da
  font di sistema (lista candidati + env `GIF_FONT`, ripiego a lettere), dama/Forza4 a
  dischi, Tris testuale. Backgammon non supportato (400).

**Frontend (`play.html` a partita conclusa + admin):** pannello «🎬 Moviola» (⏮◀▶⏭,
clic sul log per saltare, textarea nota con salvataggio), «🔬 Analizza la partita»
(polling; etichette ?? ? ?! nel log con tooltip della mossa migliore + grafico SVG
dell'andamento ±5 pedoni), «🎞️ Esporta GIF» (link diretto al backend). Card «🥊
Sparring» in Admin (form + risultato con stima ± margine). Note visibili nello storico
della scheda giocatore.

**Test (+5, 156 verdi):** partita-cavia = matto dell'imbecille; replay (5 posizioni),
note nello storico (cancellazione, 400 fuori range), analisi con finto Stockfish
interattivo (4 evals, cache `analysis_json`), GIF reale (magic bytes), sparring (401
senza token, 409 per zeus, patte col finto motore → stima = Elo del preset).
**Dal vivo (Stockfish 18 vero):** analisi corretta — 1.f3 marcata ?!, 3.g4 marcata ??
con suggerimento b1c3, matto a −10000; GIF 464×464 valida; nota persistita; 0005
auto-applicata.

---

## 2026-07-06 — Stockfish come processo persistente

**Richiesta (utente):** implementare Stockfish come processo persistente (voce TODO:
lock al posto dell'avvio one-shot per mossa, ~100 ms risparmiati a mossa).

**Implementazione (`opponents/stockfish.py`):**

- **`_PersistentEngine`** (singleton di modulo + `threading.Lock`: le ricerche dei
  worker sono serializzate — la CPU è comunque il collo di bottiglia e UCI non è
  concorrente). Stato ricordato fra le mosse: opzioni correnti e ultima posizione.
- Handshake `uci`/`uciok` **una volta sola** allo spawn; opzioni di forza inviate
  **solo quando cambiano** (diff), con LimitStrength sempre dichiarato esplicitamente
  — col processo vivo i valori vanno anche RIPRISTINATI (Pan→Zeus in IA-vs-IA);
- **`ucinewgame` solo a partita nuova** (la posizione non è la continuazione della
  precedente): nelle continuazioni le hash table restano calde;
- watchdog per ricerca (movetime + margine): su timeout il processo viene ucciso e la
  richiesta successiva fa il **respawn automatico**; pipe rotta PRIMA della ricerca →
  un retry con respawn; cambio `stockfish.path` → nuovo processo. In ogni errore →
  `None` → ripiego sul giocatore locale (invariato);
- `quit` SOLO alla chiusura (shutdown/atexit/respawn), mai durante il gioco (il vecchio
  bug del quit-durante-go resta documentato); `shutdown()` pubblico per test/riavvii.
- `verify()` (diagnostica admin) resta one-shot per isolare il test del binario, ma
  riporta anche lo stato del persistente: «PID …, N ricerche servite».

**Test (16 nel file, 151 totali):** finti motori ora **interattivi** (ciclo su stdin,
log dei comandi ricevuti): stesso PID su più mosse, `uci` e `ucinewgame` una volta sola
nella continuazione, diff delle opzioni (Elo inviato una volta; cambio preset →
riallineo), respawn dopo crash (deterministico con `wait`) e su cambio percorso;
fixture autouse `shutdown()` per l'isolamento. **Dal vivo:** partita contro Pan — 6
risposte «stockfish» tutte dallo **stesso PID**; diagnostica admin: «Stockfish 18 …
processo persistente attivo (PID 26734, 6 ricerche servite)».

---

## 2026-07-06 — Sistema graduale di istruzione guidata (tutorial con voce)

**Richiesta (utente):** realizzare il «Sistema graduale di istruzione guidata» (voce ⭐
del TODO): lezioni a passi con posizioni preimpostate, evidenziazioni, mossa richiesta
con verifica, progressi per utente e lettura vocale di ogni passo.

**Contenuti (`backend/app/lessons/`, un modulo per gioco):**

- Helper di authoring: `sq("e2")` (coordinate scacchistiche → indice, bianco in basso,
  vale anche per la dama), `pos8({...})`, `pos_grid`, `path_task`/`cell_task`, `step`.
- **Corso di scacchi in 7 lezioni** (scacchiera/obiettivo → pedone → torre e alfiere →
  cavallo → donna e re → arrocco + en passant → matto del corridoio), **dama** (passo,
  presa obbligatoria, presa multipla, promozione), **Tris** (centro, chiudere, bloccare).
- `validate_lesson` = guardiano nei test: griglia della misura giusta, task dentro la
  scacchiera, pezzo presente sull'origine, testi non vuoti, codici unici.

**Backend:** tabella `lesson_progress` (**migrazione 0004**; unica per utente+lezione,
`last_step` che non regredisce, `completed` definitivo); router `/lessons`: indice con
progresso personale (X-Auth-Token opzionale), lezione completa (rows/cols/move_type per
il renderer), `POST /lessons/{code}/progress` autenticato (anonimi: fruizione senza
salvataggio). Passo clampato alla lunghezza della lezione.

**Frontend:**

- CSS della scacchiera **estratto in `board_css.html`** (case, pezzi a tinta piena,
  temi, tavolo backgammon) e incluso da play.html E dalla pagina lezione: un solo posto
  da mantenere (verificato che la pagina di gioco conservi i temi).
- **«Impara»** in navbar → indice per gioco (badge «✓ completata», «riprendi dal passo
  N», pulsanti Inizia/Riprendi/Ripassa) e pagina lezione: scacchiera con evidenziazioni
  (`.hl`), task verificato dal client (clic origine→destinazione, o casella nel Tris;
  a mossa giusta il pezzo si sposta con feedback, a mossa sbagliata suggerimento),
  passi avanti/indietro, ripresa automatica dall'ultimo passo raggiunto.
- **Voce**: 🔊 legge il passo via `GET /tts` (italiano/Piper); «voce automatica» ricordata
  in localStorage. TTS assente → la lezione resta testuale (nessun errore visibile).

**Test (+4, 148 verdi):** integrità di TUTTE le lezioni, helper coordinate, endpoint
(anonimo/404), flusso progressi (401 anonimo, non-regressione, completed definitivo,
clamp). **Dal vivo:** migrazione 0004 auto-applicata; `/impara/` e `/impara/chess-pawn/`
renderizzati; progresso salvato via API e visibile nell'indice; pagina di gioco intatta.

---

## 2026-07-06 — Servizio TTS multi-motore con gestione delle lingue (Piper + KittenTTS)

**Richiesta (utente):** gestione delle lingue + integrazione di **Piper TTS**, risolvendo
la voce «Servizio TTS nel backend» del TODO: un servizio che integri **sia** KittenTTS
**sia** Piper.

**Servizio (`backend/app/tts.py`):**

- Astrazione multi-motore: registro `ENGINES = {"kitten", "piper"}` (funzioni
  `(testo, voce, velocità, percorso)` — monkeypatch-abile nei test). **La lingua decide
  il motore** tramite i parametri `tts.voice_it` / `tts.voice_en` in formato
  **`motore:voce`**: default `piper:it_IT-paola-medium` (italiano) e
  `kitten:expr-voice-2-f` (inglese). Nuova lingua = voce in `LANG_SETTINGS` + parametro.
- **Import pigri** e modelli in RAM dopo il primo uso; motore assente → **503 spiegato**
  (il tutorial resterà testuale). Voce Piper **scaricata da HuggingFace al primo uso**
  in `backend/tts_voices/` (subprocess `piper.download_voices`; fix macOS: bundle
  `certifi` in `SSL_CERT_FILE`, il Python di python.org non vede i certificati).
- **Cache su disco** (`backend/tts_cache/`, gitignored): chiave
  sha256(motore|voce|velocità|testo normalizzato), pubblicazione **atomica**
  (tmp+rename), un solo thread di sintesi (lock). Frasi fisse del tutorial → una
  sintesi sola, poi ~0,1s.
- Parametri categoria **«Voce»**: `tts.enabled`, `tts.default_lang` (it),
  `tts.voice_it`, `tts.voice_en`, `tts.speed`, `tts.max_chars` (300).

**Endpoint (`routers/tts.py`):** `GET /tts?text&lang&speed` → WAV (FileResponse);
`GET /tts/status` → motori/voci per lingua, disponibilità (senza effetti collaterali),
statistiche cache. **Admin**: card «🔊 Voce sintetica» con stato per lingua e
**anteprime `<audio>`** che chiamano direttamente il backend.

**Licenza (decisione):** `piper-tts` 1.4.2 è **GPL-3** → dipendenza **opzionale**, NON
in requirements (il progetto è MIT): si abilita con **`make piper`** (scelta esplicita
dell'operatore, documentata anche in requirements.txt). KittenTTS (Apache 2.0) resta
dipendenza normale. Senza Piper: 503 sull'italiano, inglese funzionante.

**Test (+4, 144 verdi):** motori finti iniettati in `ENGINES` (nessun download): routing
it→piper / en→kitten, cache (2ª richiesta senza sintesi, spazi normalizzati), 400
(vuoto/troppo lungo/lingua ignota), 503 (disattivato; motore rotto, senza file sporchi),
`/tts/status`. Cache dei test isolata via `TTS_CACHE_DIR`/`TTS_VOICES_DIR` (conftest).
**Dal vivo:** italiano 8,3s alla prima frase (incluso download voce ~60 MB) poi ~1s;
inglese 4,2s; cache 0,09s con file identico; anteprime funzionanti nella pagina Admin.

---

## 2026-07-05 — Concorrenti IA multipli (un provider per lato) + Gemini e Grok

**Richiesta (utente):** «Concorrenti IA multipli» (voce ⭐ del TODO): avversari IA
selezionabili al setup («gioca contro Claude», «gioca contro Gemini», …), ognuno con la
propria configurazione nella pagina Provider IA; catalogo esteso con Gemini e Grok.

**Backend:**

- Catalogo (`ai_providers.py`): aggiunti **Gemini** (Google, endpoint OpenAI-compatible
  `…/v1beta/openai`, modello `gemini-2.5-flash`) e **Grok** (xAI, `https://api.x.ai/v1`,
  `grok-4`); la pagina Provider IA li mostra da sola (template dinamico). Nuovi helper:
  `is_known`, `provider_label`, **`get_config(db, code)`** (config con token di un
  provider SPECIFICO; `get_active_config` ora è un caso particolare).
- **Migrazione 0003**: colonne `game_sessions.x_ai_provider` / `o_ai_provider` —
  il concorrente scelto per il lato; None = provider attivo globale (storico).
- `PlayerSpec.provider` (validato: 400 «Provider IA sconosciuto»); `_view` espone
  per lato `provider` + `provider_label`.
- `gameplay.advance_ai`: provider risolto **per lato** con memoizzazione
  (`provider_for(player)`) — in IA-vs-IA i due lati possono usare modelli diversi
  (es. Claude contro Gemini). Ripiego sul giocatore locale invariato (token assente,
  errore di rete): la partita non si blocca mai.

**Frontend:**

- Setup partita: le voci **«IA — Claude (Anthropic)» / «IA — Gemini (Google)» /
  «IA — Grok (xAI)» / Qwen / OpenAI** vengono generate dal catalogo (una per provider,
  «(token mancante)» se non configurato) accanto a «IA via API (provider attivo)» e ai
  preset Stockfish; il form invia `{"type":"ai","provider":<codice>}`.
- Intestazione di partita: per i lati IA compare il concorrente («IA — Grok (xAI)»).

**Test (+4, 140 verdi):** catalogo con Gemini/Grok (senza mai esporre `api_key`),
sessione con concorrenti diversi per lato (etichette in vista, ripiego locale senza
token), 400 su provider sconosciuto, `provider=None` = comportamento storico.
**Dal vivo:** migrazione 0003 auto-applicata al reload; sessione Claude-vs-Grok creata
via API con etichette corrette; voci presenti nella pagina `/gioca/`.

**Prospettiva (nuova voce TODO):** profilo/punteggi per concorrente e classifica delle
IA, tornei IA-vs-IA fra provider.

---

## 2026-07-05 — Gioco a distanza fra client diversi + Community (presenza e badge)

**Richiesta (utente):** partite in tempo reale fra giocatori su client differenti, con
client del tutto indipendenti (fra loro e contro IA); gamification: **badge di presenza
online** e **badge del punteggio complessivo**; area **Community** con i giocatori
connessi.

**Backend:**

- **Migrazione 0002** (prima revisione del nuovo workflow): `users.last_seen_at`
  (presenza) e `game_sessions.remote` (partita a distanza). Applicata da sola al riavvio.
- **`POST /auth/heartbeat`** (X-Auth-Token) rinnova la presenza; il login rende online,
  il **logout esplicito mette subito offline**. "Online" = visto entro
  `community.online_window_s` (nuovo parametro, default 120s, categoria Community).
- Nuovo router **`community.py`**: `GET /community/online` (giocatori connessi +
  `universal_points` per il badge) e `GET /community/my-games` (partite in corso del
  giocatore autenticato, con `my_turn` — è così che lo sfidato SCOPRE la sfida).
- **Partite remote**: `SessionCreate.remote`; in `make_move`, se la sessione è remota,
  la mossa richiede il **token del giocatore al tratto** (401 senza token, 403 se di un
  altro) — i client non sono fidati, l'autorità è il server. **Hotseat invariato**
  (nessun token). `UserOut.universal_points` per i badge.

**Frontend:**

- **Community** (`/community/`): giocatori online (pallino verde + pill punti + «⚔️
  Sfida») e «Le tue partite in corso» («Tocca a te!»); entrambe le liste si
  auto-aggiornano (polling di `community.json`, che fa anche da heartbeat).
- **Navbar**: badge presenza + badge punti accanto all'alias (aggiornati ogni 30s);
  link Community.
- **Setup partita**: casella «Partita a distanza»; «Sfida» precompila (io X, sfidato O,
  remota). Le mosse dal frontend portano l'X-Auth-Token della sessione Django.
- **`play.html`**: in partita remota il client comanda **solo il proprio lato**
  (`MY_SIDE` da `players.*.user_id`, `canAct()` su input e pulsanti); il polling già
  usato per l'IA ora copre anche l'**avversario umano remoto** («In attesa della mossa
  dell'avversario…») e gli spettatori; hotseat identico a prima.

**Test (+4, 136 verdi):** presenza (heartbeat/logout), enforcement remoto
(401/403/200/200 sui due lati), hotseat senza token, my-games per entrambi. Test di
adozione migrazioni rifatto fedele (DB portato a 0001 senza `alembic_version` → adozione
→ 0002 applicata). **Verifica dal vivo** sul backend reale: 401/403/200, presenza e
sfida visibili a entrambi i giocatori; `alembic current` → 0002.

---

## 2026-07-05 — Migrazioni Alembic (fine dell'era create_all)

**Richiesta (utente):** procedere con le migrazioni ad Alembic.

**Impianto:**

- `backend/alembic.ini` (senza URL: percorsi con `%(here)s`, indipendenti dalla CWD) +
  `backend/migrations/` (`env.py`, `script.py.mako`, `versions/`). L'URL arriva da
  `app.database.DATABASE_URL` (quindi da `.env`), oppure dall'override programmatico
  `config.attributes["sqlalchemy_url"]` usato da runner e test. `render_as_batch=True`
  per gli ALTER futuri su SQLite.
- **Revisione 0001 «schema iniziale»** (autogenerate contro DB vuoto): tutte le 11 tabelle.
- **`app/db_migrate.py`**: `run_migrations()` chiamata dal lifespan al posto di
  `create_all`. Tre casi: DB nuovo → `upgrade head`; DB migrato → applica solo le revisioni
  mancanti; DB dell'era create_all senza `alembic_version` → **adozione** con `stamp 0001`
  se lo schema corrisponde alla baseline (marcatori: `users.is_approved` +
  `auth_sessions`), altrimenti **errore chiaro** (eliminare il DB). Guardia per-processo:
  i test aprono l'app decine di volte, Alembic gira una volta sola per URL.
- `make migrate` (upgrade head) e `make migration m="descrizione"` (autogenerate).

**Nuovo workflow per i cambi di schema:** modificare i modelli →
`make migration m="..."` → riavviare (o `make migrate`). NIENTE più `rm backend/scacchi.db`.

**Test (+3, 132 verdi):** allineamento migrazioni↔modelli via `compare_metadata`
(fallisce elencando le differenze se si tocca un modello senza generare la revisione),
adozione del DB legacy, rifiuto con errore esplicito dei DB più vecchi della baseline.
**Verifica dal vivo:** il backend in `--reload` si è riavviato durante il lavoro e ha
adottato da solo il `scacchi.db` di sviluppo (`alembic current` → `0001 (head)`); API ok.

---

## 2026-07-05 — Registrazione con approvazione del super admin + autenticazione (login/logout)

**Richiesta (utente):** la registrazione dei giocatori diventa una richiesta che **solo il
super admin accetta**; autenticazione con **login/logout e sessione**, password **già
hashate in anagrafica**.

**Backend:**

- `User.is_approved` (default **False**: ogni registrazione nasce «in attesa») e nuova
  tabella **`auth_sessions`** (token opaco, scadenza, pulizia pigra delle scadute).
  **⚠️ cambio schema senza migrazioni** → ricreare `backend/scacchi.db`.
- `POST /users` = richiesta di registrazione (password opzionale a livello API, hashata
  subito con PBKDF2 — security.py già esistente; mai salvata in chiaro).
- **`POST /users/{id}/approve`** e **`DELETE /users/{id}`** (respinta, solo richieste in
  attesa: 409 su utenti approvati) — entrambi dietro `require_admin` (X-Admin-Token).
- Nuovo router **`auth.py`**: `POST /auth/login` (identificazione con alias **o** email;
  401 identico per utente inesistente/senza password/password errata — niente enumerazione;
  403 «in attesa di approvazione» solo a password verificata), `GET /auth/me`
  (X-Auth-Token), `POST /auth/logout` (idempotente, 204). Durata sessione = parametro
  **`users.session_hours`** (default 720 ore, categoria Utenti).

**Frontend (senza DB proprio):**

- Sessione Django su **cookie firmato** (`SESSION_ENGINE=signed_cookies` + middleware):
  nel cookie solo token backend e {id, alias} del giocatore — mai la password.
- Pagine: **Accedi** (`/accedi/`, alias o email + password) ed **Esci** (POST); navbar con
  «👤 alias» → scheda personale; context processor `auth_user` per tutti i template.
- «Giocatori → Richiedi registrazione»: password obbligatoria con conferma (solo controllo
  locale); esito: «richiesta inviata, serve l'approvazione». Lista giocatori con badge
  «in attesa di approvazione».
- Pagina **Admin**: sezione «Richieste di registrazione in attesa» con Approva/Respingi
  (token super admin nel form, come per i parametri).

**Test (+5, 129 verdi):** richiesta→login 403; approvazione solo con token e login/me/
logout dopo; 401 indistinguibili; respinta solo per richieste in attesa; scadenza sessione
pilotata da `users.session_hours` (0 ore → token già scaduto).

---

## 2026-07-05 — Pezzi a tinta piena + contrasto WCAG 2.1 (correzione estetica)

**Richiesta (utente):** pezzi in **tinta piena** e contrasto sufficiente fra i colori
della scacchiera e quelli dei pezzi (WCAG 2.1); riferimento in
`temi/scacchi-posizione-iniziale-pezzi.jpg` (bianchi pieni bordati di scuro, neri pieni).

**Causa:** i glifi Unicode del lato bianco (♔♕… ⛀⛁ ○) sono *vuoti* per disegno, quindi
non esiste "tinta" da riempire; inoltre i pezzi chiari sulle case chiare dei temi
(es. bianco su crema del tema legno ≈ 1.3:1) erano quasi invisibili.

**Soluzione (solo `play.html`):**

- `displayOf()` mappa ogni glifo bianco sul **glifo pieno** equivalente
  (♔→♚ … ♙→♟, ⛀→⛂, ⛁→⛃, ○→●): il colore del lato lo decide il CSS, `pieceClass`
  continua a leggere il simbolo originale del motore (stato invariato).
- CSS dei temi: via le ombre sfumate, il lato chiaro ha un **bordo scuro**
  (`-webkit-text-stroke` 2px + `paint-order:stroke fill`), il lato scuro è pieno senza
  bordo; nel backgammon entrambe le pedine hanno il bordo di tono opposto (1.5px).
- **Contrasti verificati** (script luminanza relativa, soglia SC 1.4.11 ≥3:1): tutte le
  26 coppie pezzo/casa passano; minimo 4.47:1 (bordo bianco su casa verde smeraldo),
  il resto ≥4.5:1. Sintassi JS ricontrollata con `node --check`. 124 test verdi.
- **Ritocco successivo (stessa giornata):** pezzi il **15% più grandi** — nuova costante
  `PIECE_SCALE = 0.83` (era 0.72 duplicato fra celle e flyer).

---

## 2026-07-05 — Opzioni giocatore: temi scacchiera/pezzi, segno del Tris, tavolo backgammon

**Richiesta (utente):** il giocatore sceglie l'estetica di scacchiera e pezzi; il tavolo
del backgammon deve essere quello **originale**; nel Tris ognuno sceglie la **forma del
proprio segno**. Tutto nelle **opzioni utente/giocatore**.

**Backend:**
- **`User.prefs_json`** (nuova colonna, default `{}`) + proprietà `User.prefs`;
  **⚠️ cambio schema senza migrazioni** → ricreare `backend/scacchi.db`.
- Nuovo registro **`user_prefs.py`** (distinto dai parametri di programma: preferenze
  personali, nessun token): `board_theme` (classico/legno/smeraldo/ghiaccio) e
  `tris_mark` (✕ ✖ ★ ☆ ♥ ◆ ▲ o X/O; vuoto = default). Endpoint
  **`PUT /users/{id}/prefs`** con validazione (400 su valori non ammessi); prefs esposte
  in `UserOut`/scheda giocatore.
- Vista di sessione: per lato espone `board_theme` e `mark` (IA = default); **collisione
  segni** risolta (stesso segno per entrambi → il lato O ripiega sul default).

**Frontend:**
- Scheda giocatore: sezione **«Opzioni giocatore»** (form tema + segno, salvataggio
  senza token).
- `play.html`: **temi CSS** `t-legno`/`t-smeraldo`/`t-ghiaccio` (case e colori dei pezzi,
  flyer inclusi; vale per scacchi e dama; in partita fra umani vince il tema di X);
  segni Tris via `displayOf()` (lo stato resta X/O del motore, la traduzione è solo al
  momento del render: celle, flyer, ghost); `pieceClass` ora guarda l'**ultimo
  carattere** (le celle del backgammon sono «2○»/«5●»).
- **Tavolo classico del Backgammon** (non tematizzabile): 24 punte **triangolari
  alternate** disegnate come SVG di sfondo (il testo delle pedine resta sopra), campo in
  legno con cornice, barra centrale e vasche d'uscita dedicate; pedine chiare/scure ad
  alto contrasto.

**Test (+3, 124 verdi):** aggiornamento/lettura/reset prefs, validazione (tema o segno
non ammesso → 400, utente inesistente → 404), esposizione nella vista di sessione con
collisione risolta e default per l'IA. **Verifica dal vivo:** prefs salvate via API;
pagina scacchi con `t-legno`; pagina Tris con segno «★»; pagina backgammon con
`bg-board`/punte; form nella scheda giocatore.

---

## 2026-07-05 — KittenTTS diventa submodule git + dipendenza del backend

**Richiesta (utente):** aggiungere KittenTTS come submodulo/dipendenza.

**Realizzato:**
- La copia in `integrazioni/KittenTTS` era già un **clone git** di
  `github.com/KittenML/KittenTTS`: registrata come **submodule** (`.gitmodules`),
  pinnata al commit upstream `9f3e0d8` (v0.8.1). Prima della registrazione il clone è
  stato **ripristinato allo stato upstream**: le uniche modifiche locali erano la
  riformattazione accidentale di un mio `ruff format .` girato prima di escludere
  `integrazioni/` dal lint (nessuna modifica funzionale — verificato dal diff).
- **Dipendenza del backend**: `./integrazioni/KittenTTS` in `backend/requirements.txt`
  (path relativo alla root: come installa `make install`); `make install` ora esegue
  prima `git submodule update --init`. Verificato: `pip install -r
  backend/requirements.txt` dalla root installa e `from kittentts import KittenTTS`
  funziona.
- README (Avvio rapido): nota sul clone `--recursive` / `git submodule update --init`.

**Nota per chi clona:** senza inizializzare il submodule l'installazione dei
requirements fallisce sul path — è il comportamento voluto (dipendenza esplicita).

---

## 2026-07-05 — Valutazione KittenTTS per la futura sezione di istruzione guidata

**Contesto (utente):** in `integrazioni/KittenTTS/` c'è il progetto **KittenTTS** (TTS che
sintetizza il parlato da testo), da integrare per la **sezione di istruzione**: un sistema
graduale di istruzione guidata per insegnare i vari giochi, con voce.

**Analisi del progetto:** libreria open source (Apache 2.0, compatibile con MIT) basata su
**ONNX**, solo CPU, modelli 15–80M (25–80 MB) scaricati da HuggingFace al primo uso e poi
in cache; 8 voci; API minima: `KittenTTS(modello).generate(text, voice, speed)` → audio
numpy a 24 kHz. Dipendenze via pip (incluso `espeakng_loader` che porta con sé la libreria
espeak: niente brew — utile con i Command Line Tools rotti).

**Fattibilità verificata dal vivo** (installato nel venv, modello *nano* 15M): caricamento
16s la prima volta (download HF) poi immediato; sintesi ~1–2s per 5–7s di audio su CPU.
File di prova generati (inglese e italiano).

**⚠️ Limite chiave — solo inglese:** il fonemizzatore è cablato `en-us`
(`onnx_model.py:81`) e la normalizzazione del testo è tutta inglese; il testo italiano
viene sintetizzato con pronuncia anglicizzata (verificato). Per un tutorial in italiano
serviranno voci italiane: opzione principale **Piper TTS** (stessa forma: ONNX/CPU),
dietro un'astrazione comune del servizio TTS. Dettagli e piano completo del sistema di
istruzione guidata annotati in **TODO.md** (sezione «Istruzione guidata (tutorial) + voce
sintetica»): contenuti a passi con posizioni preimpostate ed evidenziazioni, progressi per
utente, endpoint `GET /tts` con cache su disco e import pigro (dipendenza opzionale).

**Nota:** `integrazioni/` resta esclusa dal lint e **non versionata** (scelta da
confermare con l'utente); `kittentts` è ora installato nel venv di sviluppo ma NON è
ancora una dipendenza del backend (lo diventerà — opzionale — con il servizio TTS).

---

## 2026-07-05 — Backgammon: primo gioco stocastico (i nodi del caso diventano realtà)

**Obiettivo:** implementare il Backgammon rispettando l'architettura generale (una
directory per gioco, una classe per file, interfaccia `Game`) con codice molto commentato.

**Architettura — i nodi del caso, previsti dal giorno uno, ora funzionano:**
- `engine/common/game.py`: completato il contratto con **`apply_chance`** (applica un
  evento aleatorio a un nodo del caso), `describe_chance` (notazione per il log) e
  `view_status` (riga informativa per il client, es. i dadi del turno).
- **Il SERVER tira i dadi** (`gameplay.resolve_chance`): arbitro imparziale — nessun
  client può scegliere o ripetere il tiro. Estrazione pesata su `chance_outcomes`,
  registrata nel log («🎲 5-3»; se ingiocabile: «— nessuna mossa possibile, il turno
  passa» e si continua a tirare). Chiamata pigra dalle letture di stato, prima/dopo le
  mosse umane, nel ciclo del worker IA e nel batch (lì senza log).

**Il gioco (`engine/backgammon/`, `game.py` + `state.py`):**
- Stato: 24 punte con segno (+X/−O), barra, pedine fuori, giocatore, **dadi residui**
  (None = nodo del caso). X muove 23→0 (casa 0..5), O all'opposto.
- Modello del turno: **un dado = una mossa**; doppio = 4 mosse; il turno passa da solo
  quando i dadi finiscono o nessuno è giocabile (`_normalize`).
- Regole: punte **bloccate** con ≥2 avversarie; **colpo** della singola (va sulla barra,
  notazione «13/8*»); **rientro obbligatorio** dalla barra; **uscita** con tutte in casa
  (dado esatto sempre; maggiore solo dalla punta più lontana). Vince chi porta fuori 15.
- Vista a griglia **2×14** per il frontend generico: punte 12..23 sopra, 11..0 sotto,
  colonne extra per barre e uscite; celle «2○»/«5●». Notazione a pip («13/8», «bar/22»,
  «6/off»). IA locale greedy dado per dado (`search_depth=1`, euristica: pip, pedine
  fuori, blot, barra — l'expectiminimax è in TODO).
- **Semplificazioni documentate:** niente tiro iniziale "un dado a testa" (inizia X),
  niente regola del dado maggiore obbligatorio, niente cubo/gammon.

**Integrazione:** registrato nel registry (→ `playable` automatico); vista di sessione
con `status_line` («Dadi da giocare: 5 3 — obbligo di rientro…»); frontend: il
backgammon usa la selezione origine→destinazione esistente + riga di stato. Il batch
IA-vs-IA risolve i nodi del caso in linea.

**Extra:** esclusa dal lint la nuova directory `integrazioni/` (codice esterno
dell'utente, es. KittenTTS — non tracciata e non committata).

**Test (+13, 121 verdi):** motore (nodi del caso e probabilità 21 tiri, doppi=4 mosse,
punte bloccate, colpo→barra, rientro obbligatorio, uscita esatta/scarto, passaggio del
turno con tiro ingiocabile, vittoria, serializzazione, viste, euristica simmetrica) +
sessioni end-to-end (tiro del server già alla creazione, notazione a pip nel log, turno
che passa con tiro dell'avversario pronto, partita contro l'IA). Aggiornato il test del
flag `playable`.

**Verifica dal vivo:** partita umano-vs-IA completa di un giro: «🎲 5-3 → 6/3, 8/3 →
🎲 6-4 (IA) → 8/2, 6/2 → 🎲 3-2» con riga di stato e mosse giocabili corrette.

---

## 2026-07-05 — Animazioni per intero: percorsi a tappe (cavallo a "L", prese multiple, promozioni)

**Richiesta (utente):** ogni mossa va visualizzata per intero — il cavallo deve fare tutto
il suo percorso (non comparire sulla casella d'arrivo), la doppia presa della dama va
mostrata salto per salto, e nella promozione prima si muove il pezzo e poi si crea la dama.

**Realizzato (solo `play.html`, nessuna modifica al backend):**
- **`flyPiece`**: il pezzo vola lungo una **sequenza di caselle**, un segmento alla volta
  (`ui.anim_ms` per segmento), con callback a ogni tappa e all'atterraggio.
- **Cavallo a "L"** (`knightWaypoint`): waypoint intermedio — prima il lato lungo, poi
  quello corto.
- **Catena di prese della dama** (`draughtsChain`): ricostruita dal diff (ogni salto
  scavalca una vittima adiacente in diagonale e atterra due caselle oltre); ogni vittima
  **sparisce nel momento in cui viene scavalcata**. Se la ricostruzione fallisce → volo
  diretto (fallback sicuro).
- **Vittime e pezzi catturati visibili** finché il pezzo in volo non li raggiunge
  (`showGhost`): la "mangiata" si vede accadere; negli scacchi il pezzo catturato resta
  sulla casella finché chi cattura non ci atterra sopra (en passant incluso).
- **Promozioni**: vola il **pezzo originale** (`prev[from]`), che all'atterraggio si
  trasforma in dama/donna con un "pop" — prima il movimento, poi la creazione.
- `syncCell` riallinea la singola casella allo stato reale a fine volo; suono all'ultimo
  atterraggio (più grave con cattura).

**Verifiche:** sintassi JS validata con `node --check` (script estratto con i tag Django
sostituiti); pagina resa con tutte le nuove funzioni; **108 test** verdi (nessun tocco al
backend); lint pulito.

---

## 2026-07-05 — Il ritardo minimo vale per OGNI mossa dell'IA (niente risposte "incollate")

**Richiesta (utente):** evitare le mosse consecutive — tra una mossa e l'altra deve esserci
comunque un ritardo di ~1 secondo, configurabile da admin.

**Fix:** il ritmo di visione introdotto nella voce precedente ora si applica a **ogni mossa
dell'IA**, non solo alle partite IA-vs-IA e alla prima mossa: anche la **risposta alla
mossa dell'umano** (tipicamente istantanea quando viene dal libro) rispetta il ritardo
minimo dalla mossa precedente. In `gameplay.advance_ai` è caduta la condizione
`both_ai or prima-mossa`: la pausa vale per tutte le mosse del worker; restano invariate
le tutele (solo in modalità asincrona; con l'orologio la pausa è "dell'arbitro").

**Configurazione:** `ai.watch_pace_ms` rietichettato «Ritardo minimo tra una mossa e
l'altra dell'IA», **default 1000 ms** (era 1200; i DB esistenti conservano il valore già
seedato — modificabile dal super admin). Override `AI_WATCH_PACE_MS` nei test (0).

**Test (+1, 108 verdi):** subito dopo la mossa dell'umano l'IA non ha ancora risposto
(solo 1 mossa nel log); la risposta arriva poi, singola. **Verifica dal vivo:** mossa umana
`e2e4` → risposta di libro `e7e6` arrivata dopo **1.14s** (attesi ≥1s).

---

## 2026-07-05 — Ritmo di visione: le mosse IA arrivano una alla volta (partite osservabili)

**Sintomo (utente):** nelle partite IA-vs-IA le prime mosse non si vedono — troppo veloci;
serve un ritardo tra una mossa e l'altra e la garanzia che la scacchiera sia disegnata
prima della prima mossa.

**Causa:** il worker IA parte alla creazione della sessione e le mosse di **libro** sono
istantanee: quando il browser carica la pagina, mezza apertura è già giocata; e tra due
polling potevano cadere più mosse (mostrate "a salti").

**Fix (`gameplay.advance_ai`):** **ritmo minimo tra le mosse IA**, applicato con una
`time.sleep` nel worker (mai nelle richieste HTTP: attivo solo in modalità asincrona):
- tra le mosse quando **entrambi i lati sono IA** (partita "da guardare");
- prima della **prima mossa della partita** quando apre l'IA (dà al browser il tempo di
  disegnare la scacchiera: la mossa arriva poi via polling, animata e col suono).
- Con l'**orologio** attivo la pausa non consuma il tempo del giocatore: è "dell'arbitro"
  (`turn_started_at` riparte a fine pausa).

**Configurazione:** parametro super admin `ai.watch_pace_ms` (categoria IA, default
1200 ms; 0 = nessun ritmo); override d'ambiente `AI_WATCH_PACE_MS` (nei test: 0).

**Test (+1, 107 verdi):** con ritmo attivo la risposta di creazione ha **0 mosse** (la
scacchiera nasce vuota) e la prima mossa IA arriva dopo, singola.

**Verifica dal vivo:** IA-vs-IA di scacchi (Stockfish Pan vs Pan): creazione con 0 mosse,
poi `e4, e5, Cf3, Cc6, Ab5, a6` una alla volta a intervalli di ~1.0–1.3s — la partita si
guarda come un video.

---

## 2026-07-05 — Orologio di gioco per gli scacchi (Blitz/Rapid/Classical/FIDE + Fischer)

**Obiettivo:** tempo permesso per le mosse, con categorie selezionabili dal giocatore e
incremento Fischer opzionale.

**Categorie** (validate dal backend, `gameplay.build_time_control`):
- **Blitz/Lampo**: <15′ a testa (minuti 1–14, default 5); **Rapid**: 15–60′ (default 25);
  **Classical**: >60′ (61–600, default 90) — per questi tre l'**incremento Fischer**
  è opzionale (0–60″ riaccreditati a ogni mossa completata, es. 3′+2″).
- **FIDE ufficiale**: parametri **fissi** — 90′ + 30″ a mossa fin dall'inizio, **+30′**
  quando il giocatore completa la sua **40ª mossa**; minuti/incremento personalizzati
  vengono rifiutati (400).

**Meccanica (server = arbitro, `gameplay.py`):**
- Colonne nuove su `game_sessions`: `tc_category/tc_base_s/tc_inc_s`, residui
  `x/o_clock_ms` (millisecondi), `turn_started_at` (l'orologio del giocatore al tratto
  scorre da qui), `finish_reason` ("time" = decisa dall'orologio).
  **⚠️ Cambio schema senza migrazioni:** ricreare `backend/scacchi.db`.
- `consume_time` alla mossa: scala il tempo pensato, accredita il bonus
  (`_bonus_ms`: Fischer o FIDE con il +30′ alla 40ª), fa ripartire l'orologio
  dell'avversario; se il residuo è esaurito → mossa rifiutata (409 «Tempo scaduto»).
- **Bandierina pigra** (`check_time`): la lettura di stato (il polling del client)
  constata la caduta anche se nessuno muove più. Esito: vince l'avversario, **patta se
  gli resta il re nudo** (semplificazione della regola FIDE, documentata).
- **IA sotto orologio**: il suo tempo scorre mentre pensa; il budget di riflessione
  (motore interno e Stockfish) è limitato a ~1/10 del residuo così non perde per tempo;
  se la bandierina cade durante la pensata, la mossa non viene registrata.
- Il tempo (`_now`) è centralizzato e monkeypatch-abile: i test simulano il passare dei
  minuti senza attese reali.

**API/Frontend:** `SessionCreate.time_category/time_base_min/time_inc_s`; la vista espone
`clock` (residui *vivi*, lato in corsa) e `finish_reason`. Setup con menù «Orologio (solo
scacchi)» + minuti + incremento; in partita **due orologi** sopra la scacchiera (ticchettio
client-side risincronizzato a ogni stato; al tratto evidenziato, rosso sotto i 30″; a 0 il
client chiede la constatazione al server); esito «Ha vinto X (tempo scaduto)». Testo del
setup aggiornato (era rimasto all'era-Tris).

**Test (+5, 106 verdi):** validazioni per categoria e FIDE fisso; orologio nella vista
(blitz 3′+2″ e FIDE 5400s/30″); consumo+incremento con tempo simulato (60000−10000+3000);
bandierina sulla mossa (409) e pigra sulla lettura; unit su `_bonus_ms` (FIDE 40ª) e
`_winner_on_time` (re nudo → patta).

**Verifica dal vivo:** partita Blitz 3′+2″ contro Stockfish (Pan): X pensa ~3s reali →
`x_ms` scala e riaccredita +2″; l'IA muove e riceve il suo incremento; `running` passa di
mano; orologi resi in pagina; campi orologio nel form di setup.

---

## 2026-07-05 — Animazione delle mosse + effetto sonoro (personalizzabili da super admin)

**Obiettivo:** i pezzi si muovono con un'animazione e un effetto sonoro di base; velocità e
suono personalizzabili dalla sezione admin.

**Realizzato:**
- **Animazione di scorrimento** (`play.html`): nuova `transitionBoard(next)` che confronta
  la board attuale con la nuova e **fa scivolare i pezzi** con elementi «flyer» assoluti
  sopra la griglia (transizione CSS su `transform`, accelerata dalla GPU). L'accoppiamento
  origine→destinazione avviene **per simbolo** tra caselle svuotate e occupate: copre anche
  **arrocco** (2 coppie), **en passant** e **promozione**; le origini rimaste senza
  destinazione sono catture (dama). Forza 4: la pedina **cade dall'alto** della colonna;
  Tris: comparsa con il "pop" esistente. Vale per mosse umane, risposte IA (polling e
  modalità sincrona) e partite IA-vs-IA osservate; la risincronizzazione d'errore resta
  istantanea (nessuna animazione).
- **Effetto sonoro** sintetizzato via **WebAudio** (nessun file audio da scaricare): "toc"
  percussivo a onda triangolare con glissando e decadimento esponenziale, **più grave sulle
  catture**; suona all'arrivo del pezzo. I browser attivano l'audio dopo il primo gesto
  dell'utente (listener `pointerdown` once).
- **Personalizzazione** (nuova categoria super admin **«Aspetto»**): `ui.anim_ms` (durata
  animazione, 0 = disattivata), `ui.sound_enabled`, `ui.sound_volume` (0-100). Esposti al
  frontend da `GET /config` e iniettati nella pagina di gioco come costanti JS. Nessun
  cambio di schema (i nuovi parametri si seedano da soli).
- **Refactor coerente del client**: i callback `mutate` ritornano una **copia** della board
  (niente mutazione in place); ogni aggiornamento passa da `transitionBoard`.
- **Test**: `test_public_config` esteso ai tre parametri. **101 test** verdi; lint pulito.

**Verifiche dal vivo:** `/config` espone i parametri; il super admin li elenca in
«Aspetto»; personalizzazione applicata (600ms / volume 80 → la pagina riceve
`ANIM_MS = 600`, `SOUND_VOL = 80`); nuovo JS (`transitionBoard`, `playSound`, `.flyer`)
presente nella pagina resa.

---

## 2026-07-05 — Fix forza Stockfish (bug del "quit") + sei livelli con divinità greche

**Sintomo (utente):** l'avversario Stockfish «continua ad essere debole».

**Causa trovata (bug reale):** il dialogo UCI one-shot accodava ``quit`` subito dopo
``go movetime``; Stockfish legge stdin **anche durante la ricerca** e un ``quit`` ricevuto
mentre pensa la **interrompe immediatamente** → bestmove a profondità ~1, qualunque fosse
il movetime. L'indizio c'era già: «mossa di prova: a2a3» dalla posizione iniziale — un vero
Stockfish non gioca a2a3.

**Fix (`opponents/stockfish.py`):** nuovo `_uci_dialogue` interattivo — invia i comandi,
**legge l'output fino a `bestmove`** e solo allora manda `quit`; watchdog (`threading.Timer`
→ kill) se il motore non risponde. Condiviso da `_ask_bestmove` e `verify`. Dopo il fix:
posizione iniziale @500ms → **e2e4** (prima a2a3).

**Sei livelli preconfigurati** (`stockfish.PRESETS`, nomi di divinità greche, dal più forte
al più debole): **Zeus (Extreme)** piena forza/4s, **Atena (Master)** Elo 2700/2.5s,
**Apollo (Champion)** 2350/1.8s, **Ares (Expert)** 2000/1.2s, **Hermes (Middle)** 1700/0.8s,
**Pan (Learner)** 1400/0.5s. L'Elo usa `UCI_LimitStrength`+`UCI_Elo`; il percorso del
binario resta globale; `config_for_level` applica il preset sopra la base (per lato: in
IA-vs-IA i due lati possono avere livelli diversi).

**Cablaggio:** `PlayerSpec.level` (validato: preset noto o 400), colonne
`game_sessions.x/o_ai_level`, vista con `level`/`level_label`, form di setup con le sei
voci «Stockfish — Zeus (Extreme)» … «Pan (Learner)» (valore `stockfish:<livello>` scisso
dalla vista), etichetta del livello nella pagina di gioco.
**⚠️ Cambio schema senza migrazioni** (di nuovo): ricreare `backend/scacchi.db`.

**Test (+3, 101 verdi):** preset completi e sensati (etichette con le sei difficoltà, Elo
in range e strettamente decrescenti), merge preset/base, livello esposto dalla vista e
livello sconosciuto → 400. **Verifiche dal vivo (vero Stockfish 18):** Zeus risponde in
~5s, Pan in ~1.5s, entrambi con `last_ai.source="stockfish"`; `verify` ora riporta
«mossa di prova: e2e4».

---

## 2026-07-05 — Verifica di Stockfish dall'interfaccia (+ conferma col vero Stockfish 18)

**Domanda dell'utente:** come essere sicuri che Stockfish sia installato correttamente e
davvero usato dal programma. Prima la risposta richiedeva di leggere JSON a mano; ora è
visibile dall'interfaccia.

**Realizzato:**
- **`stockfish.verify(cfg)`** (`opponents/stockfish.py`): diagnostica senza eccezioni —
  esegue il binario con un dialogo UCI minimo e riporta nome/versione dichiarati dal
  motore e la mossa di prova, oppure il motivo del fallimento (non configurato, non
  trovato, non-UCI).
- **`POST /admin/stockfish/test`** (token super admin): esito + **percorso risolto**
  (parametro `stockfish.path` → env `STOCKFISH_PATH` → PATH).
- **Pulsante «Verifica Stockfish»** nella pagina Admin (accanto a «Salva parametri»).
- **In partita**: nuova riga **«Ultima mossa IA: …»** sotto la scacchiera (libro aperture /
  Stockfish / motore interno / minimax locale / provider) — la vista espone `last_ai.source`
  per tutti i giochi; è la prova immediata di *chi* sta giocando.
- **Test** (+3, 98 verdi senza skip): `verify` con binario mancante e con finto motore;
  endpoint con 401 senza token, `ok=false` su percorso inesistente (forzato: sul PATH può
  esserci uno Stockfish vero), `ok=true` con finto binario.

**Verifiche dal vivo (l'utente ha installato Stockfish 18 in `/usr/local/bin`):**
endpoint di verifica → «Stockfish 18 — mossa di prova: a2a3», percorso risolto; partita
reale con O = Stockfish, mossa fuori libro `a2a3` → risposta `a7-a6` con
`last_ai.source = "stockfish"`. Il test `skipif` col vero binario ora gira e passa.

---

## 2026-07-05 — Tre tipi di avversario + pacchetto opponents/ (API, Stockfish, locale)

**Obiettivo:** l'avversario può essere di **tre tipi** — umano, **Stockfish (NNUE)
configurabile**, **IA via API** (Qwen, Claude, Gemini, …) — con il codice delle chiamate IA
e quello di Stockfish **separati in moduli dedicati** per leggibilità.

**Realizzato:**
- **Nuovo pacchetto `backend/app/opponents/`** (ex `ai.py`, spostato con `git mv`):
  - `api_ai.py` — avversario **IA via API**: prompt, parsing tollerante della risposta
    (`_match_move`), client OpenAI-compatible (httpx) e Anthropic (SDK), `ping` per la
    verifica credenziali. Solo chiamate remote, nessuna logica di gioco.
  - `stockfish.py` — avversario **Stockfish** via protocollo **UCI**: dialogo one-shot in
    subprocess (opzioni → posizione → `go movetime` → `bestmove`, chiuso da `quit`),
    thread-safe e senza stato; posizione come `startpos + moves` (dallo storico) o FEN
    (nuovo `Chess.to_fen`, inverso di `from_fen`). Configurabile dal super admin
    (categoria **Stockfish**): `stockfish.path` (o env `STOCKFISH_PATH`, o PATH),
    `stockfish.move_ms`, `stockfish.elo` (UCI_LimitStrength+UCI_Elo 1320-3190),
    `stockfish.skill_level` (0-20).
  - `local.py` — **giocatore locale di ripiego** (non selezionabile): motore dedicato per
    gli scacchi, minimax generico per gli altri giochi. Entra quando l'avversario scelto
    non può muovere (binario mancante, provider assente, errore di rete).
  - `__init__.py` — **dispatcher per tipo**: libro aperture per tutti → Stockfish o
    provider API secondo il tipo → ripiego locale. La `sorgente` restituita dice chi ha
    giocato davvero (book / stockfish / codice provider / engine / local).
- **Cambio di comportamento (voluto):** con avversario «IA via API» il modello remoto
  **gioca davvero** (prima, negli scacchi, il motore interno lo scavalcava sempre);
  il motore interno resta il ripiego.
- **Modello dati:** nuove colonne `game_sessions.x_ai_kind` / `o_ai_kind`
  ("ai" | "stockfish", None per umano; righe storiche con kind assente ⇒ "ai").
  **⚠️ Cambio schema senza migrazioni:** in sviluppo eliminare il DB
  (`rm backend/scacchi.db`) prima di riavviare il backend.
- **API/Frontend:** `PlayerSpec.type` ∈ {human, ai, stockfish}; la vista espone il tipo per
  lato e `last_ai.source` anche per scacchi/dama (prima solo per i giochi a cella); setup
  partita con tre scelte («Umano», «IA via API (Qwen, Claude, …)», «Stockfish (motore)»);
  pagina di gioco con etichetta del tipo; batch invariato (solo tipo "ai").
- **Test** (95 totali, +8): ponte UCI provato con un **finto motore** (script shell che
  risponde `bestmove`), rifiuto di bestmove illegale, ripiego sul locale, end-to-end di una
  sessione con lato "stockfish", round-trip `to_fen`/`from_fen`; test col vero Stockfish
  marcato `skipif` (binario assente su questa macchina). Lint pulito.

**Verifiche dal vivo:** sessione scacchi con O = Stockfish (finto binario via
`STOCKFISH_PATH`): mossa fuori libro `a2a3` → risposta `e7e5` arrivata **dal ponte UCI**
(tipo del lato "stockfish" esposto dalla vista); ripiego sul motore interno verificato con
binario assente.

---

## 2026-07-05 — Refactor del motore: una directory per gioco, common/, una classe per file

**Obiettivo:** facilitare lettura e manutenzione raggruppando i file di ogni gioco in una
directory dedicata, con le parti comuni in ``common/`` e **ogni classe in un file separato**.

**Nuova struttura di `engine/`** (i file sono stati spostati con `git mv`, storia preservata):
- `common/` — `game.py` (interfaccia astratta **Game**), `outcome.py` (**Outcome**),
  `registry.py` (registro dei giochi). Prima erano in `core.py` + `registry.py`.
- `tictactoe/`, `connect4/`, `draughts/` — per ciascuno `game.py` (classe delle regole) e
  `state.py` (classe di stato, prima nello stesso file).
- `chess/` — `game.py` (**Chess**), `state.py` (**ChessState**), `board.py` (costanti e
  funzioni di scacchiera condivise da regole e motore: `is_attacked`, `king_square`, …,
  rinominate senza underscore perché ora inter-modulo), `engine.py` (ricerca, ex
  `chess_engine.py`), `context.py` (**SearchContext**, ex `_Ctx`), `errors.py` (**TimeUp**),
  `openings.py` (libro, invariato).
- Rimossi `engine/core.py`, `engine/registry.py`, `engine/games/`.

**Import aggiornati:** il pacchetto `engine` ri-esporta l'API stabile
(`from engine import Game, get_game, is_playable, …`); il backend ora importa da lì
(`gameplay`, router `sessions`/`games`) e da `engine.chess` (`openings`, `Chess`);
test del motore e del backend allineati ai nuovi percorsi. Rimossa la funzione morta
`style_from_profile` (superata da `chess_profile._style`).

**Convenzione documentata nel README:** aggiungere un gioco = nuova directory
`engine/<gioco>/` con `game.py`/`state.py` + registrazione in `common/registry.py`.

**Verifiche:** lint pulito; **87 test** verdi (invariati); backend avviato dal vivo con la
nuova struttura → `/games` risponde col catalogo corretto. Aggiornato l'albero della
struttura nel README.

---

## 2026-06-28 — Libro di aperture ampliato (per posizione, con trasposizioni e file esterno)

**Obiettivo (da TODO.md):** libro di aperture più ampio.

**Realizzato:**
- **Libro integrato ampliato** (`engine/games/openings.py`): da 22 a **75+ linee**, con le
  varianti principali e linee più profonde (fino a 16-17 semimosse) — Italiana (Giuoco Piano,
  Evans), Spagnola (chiusa, aperta, Berlinese, cambio), Scozzese (Mieses, classica, gambetto),
  Petroff, gambetti di Re/Danese, Viennese, Quattro cavalli, Filidor; Siciliana (Najdorf,
  Dragone-Jugoslavo, Richter-Rauzer, Scheveningen, Sveshnikov, Taimanov, Kan, Alapin, chiusa,
  Rossolimo, Moscovita, Grand Prix); Francese (avanzata, Tarrasch, Winawer, classica, cambio);
  Caro-Kann (classica, avanzata, cambio, Panov); Scandinava, Alekhine, Pirc austriaca, Moderna;
  GdD (ortodossa, Tarrasch, accettato), Slava/Semi-Slava, Catalana, Londra, Trompowsky, Colle,
  Torre; Est-Indiana (classica, Sämisch), Grünfeld, Nimzo (Rubinstein, classica), Ovest-Indiana,
  Benoni, Benko, Olandese (classica, Leningrado); Inglese (simmetrica, siciliana in contromossa),
  Réti, Attacco Est-Indiano, Bird. **Linee-base** con i nomi generici delle famiglie precedono le
  varianti: a parità di profondità vince il nome generico, poi il nome si specializza (es.
  *Difesa Siciliana* → *Siciliana Najdorf*).
- **Libro indicizzato PER POSIZIONE** (`Chess._position_book`, cache pigra di classe +
  `reset_book_cache`): la continuazione da libro vale anche quando la posizione è raggiunta per
  **trasposizione** (ordine di mosse diverso — prima il match era solo per prefisso esatto).
  I duplicati tra linee pesano la scelta casuale (le mosse più "popolari" escono più spesso).
- **Estendibilità senza codice**: `CHESS_BOOK_FILE` nel `.env` può puntare a un file di testo
  (`Nome apertura: e2e4 e7e5 …`, `#` commenta); le mosse non valide troncano la linea al
  prefisso valido in fase di indicizzazione. Documentato in `.env.example` e MANUAL.
- **Test** (`engine/tests/test_openings.py`, +5): **ogni linea integrata rigiocata col motore**
  (mossa per mossa, tutte legali), ampiezza ≥60, nome generico→specifico, **mossa da libro per
  trasposizione** (Colle via 1.Cf3), file esterno che estende e tronca. **87 test** verdi.

**Nota di misura:** un apparente rallentamento del batch Tris (47s) è risultato **rumore
termico** dei benchmark precedenti: con A/B alternato su codice corrente vs precedente i tempi
convergono (20.3s vs 20.3s). Nessuna regressione.

---

## 2026-06-28 — Mosse IA in background (fuori dalla richiesta HTTP) + TODO.md

**Obiettivo:** eliminare l'attesa bloccante della mossa IA dentro la richiesta HTTP
(2s/mossa col motore scacchi; minuti per una sessione IA-vs-IA) e creare il backlog
delle idee (`TODO.md`).

**Realizzato:**
- **`backend/app/gameplay.py`** (nuovo): logica di svolgimento partite condivisa (stato,
  log mosse, fine partita, stile avversario, `advance_ai`) + **worker in background**:
  `schedule_ai` avvia al massimo **un thread per sessione** (idempotente, set protetto da
  lock) con **sessione DB propria**; `advance_ai` ora committa **dopo ogni mossa**, così il
  polling vede la partita avanzare (IA-vs-IA compresa). Il router `sessions.py` resta solo
  HTTP e delega qui.
- **Endpoint**: `POST /sessions` e `POST /sessions/{id}/move` **rispondono subito** e
  programmano l'IA in background; `GET /sessions/{id}` fa **auto-ripristino** (se è il turno
  dell'IA e nessun worker è attivo — es. server riavviato a metà pensata — lo riprogramma,
  senza mai calcolare inline nei GET). La vista espone `ai_thinking`.
- **Configurabilità**: parametro super admin `ai.async_moves` (default sì) + override
  d'ambiente `AI_ASYNC` (nei test `0` → comportamento sincrono originale, risposte
  deterministiche). SQLite con busy-timeout 15s (scritture da due thread).
- **Frontend** (`play.html`): dopo la mossa umana (o all'apertura pagina se tocca all'IA)
  il client fa **polling** di `stato.json` (`watchAi`/`maybeWatch`): mostra «L'IA sta
  pensando…», applica la mossa IA con l'animazione quando compare, continua finché tocca
  all'IA (guardare una partita IA-vs-IA ora funziona in diretta). Errori → retry con backoff.
- **Test** (`test_async_ai.py`, +3): flusso asincrono end-to-end via polling; **idempotenza**
  dello scheduling (GET ripetuti non causano mosse doppie); modalità sincrona intatta.
  **82 test** verdi; lint pulito.
- **`TODO.md`** (nuovo): backlog completo delle idee di potenziamento (motore, IA/provider,
  giochi, piattaforma, UX, sicurezza/devops), linkato dal README.

**Verifiche dal vivo (async attivo, scacchi a budget pieno 2s):** `POST mossa` risponde in
**0.017s** con `ai_thinking=true`; il polling vede la risposta del motore (`Ng8-f6`) dopo
~1.8s; pagina partita resa col nuovo JS di polling.

**Limite noto:** scheduling **in-process** (un solo worker uvicorn); con più processi serve
una coda di lavoro vera (annotato in TODO.md).

---

## 2026-06-28 — Fix qualità IA scacchi: il motore era troppo lento per vedere la tattica

**Sintomo (utente):** l'IA «gioca al suicidio», mosse stupide e di scarso valore tattico.

**Diagnosi (misurata col benchmark):** in mediogioco il motore completava solo **profondità
2–3** (~4–8k nodi/s in puro Python) → cieco a qualunque tattica in due mosse. Cause:
`legal_moves()` usato nella ricerca **applica ogni pseudo-mossa due volte** (filtro + ricerca);
la quiescence rigenerava **tutte** le mosse legali a ogni nodo; `evaluate` costosa (~95µs);
`ChessState` dataclass frozen lento da istanziare; il jitter alla radice **inquinava alpha**.

**Correzioni (engine/games/chess_engine.py + chess.py):**
- **Ricerca pseudo-legale**: la legalità si verifica dopo l'`apply` (re sotto attacco →
  scartata); eliminato il doppio lavoro di `legal_moves` nella ricerca.
- **Quiescence su generatore di sole catture** (`Chess._capture_moves`: catture, promozioni,
  en passant) + **delta pruning**; ordinamento MVV-LVA leggero.
- **`evaluate` a passaggio singolo** con tabelle precalcolate per carattere-pezzo (materiale+PST
  già col segno, niente `upper()`/mirror a runtime); torri raccolte al volo.
- **`ChessState` → NamedTuple** (istanziazione molto più rapida; `apply` ne crea una per nodo).
- **Null-move pruning**, **estensione di scacco** (le sequenze forzate vengono risolte), **LMR**
  (mosse quiete tardive ridotte, ri-cercate solo se promettono), punteggi di matto normalizzati
  nella TT, history heuristic con tetto.
- **Anti-ripetizione**: le posizioni già occorse nella partita (ricostruite dallo storico UCI)
  valgono patta in ricerca → niente rimescolii senza scopo.
- **Jitter corretto**: scelta casuale tra mosse quasi-ottimali **dopo** la ricerca (non altera
  più alpha né i punteggi).
- **Sviluppo in apertura**: penalità per la sortita precoce della donna coi minori a casa
  (prima fuori libro giocava `Qf6` alla terza mossa; ora sviluppa, es. `Nc6`).
- Extra dalla revisione: confronto `ADMIN_TOKEN` in **tempo costante** (`secrets.compare_digest`);
  budget motore **limitato a 300ms** nelle sessioni IA-vs-IA (girano inline nella richiesta);
  `_king_square` via `tuple.index`; annotazioni tipo sulle board.

**Risultati misurati:** nps ×2.5–5 (10–20k), profondità 4–6 (prima 2–3) + estensioni;
partita di verifica contro il vecchio minimax: **vittoria per scacco matto** in 67 semimosse
con materiale in crescita costante (0 → +12), nessun pezzo regalato. Dal vivo: risposta dal
libro istantanea; mossa fuori libro in ~2s (budget rispettato). **79 test** verdi; lint pulito.

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
