# ASIS — Attività completate

> Registro delle voci di backlog **realizzate**, spostate qui da [TODO.md](./TODO.md)
> per tenere il backlog snello. Ogni voce conserva il testo originale della spunta;
> il racconto completo di ogni step è in [HANDOFF.md](./HANDOFF.md).

## Priorità alta

- [x] ⭐ **Mossa IA fuori dalla richiesta HTTP** — l'IA pensa in background e il client
  fa polling: niente attese bloccanti (2s/mossa) né richieste che durano minuti (IA-vs-IA).
- [x] ⭐ **Autenticazione dei giocatori** — login/logout con sessione, password hashate in
  anagrafica; la registrazione è una richiesta che solo il super admin accetta. Prossimo
  passo: usare l'identità loggata per vincolare mosse e registrazione partite al giocatore.
- [x] **Migrazioni Alembic** — lo schema vive in `backend/migrations/`; l'avvio applica le
  revisioni da solo (adozione automatica dei DB `create_all` a baseline). Resta da provare
  PostgreSQL in produzione.
- [x] ⭐ **Gioco a distanza in tempo reale** — partite umano-vs-umano su dispositivi diversi
  con polling strutturato (mosse col token del giocatore al tratto), presenza online
  (heartbeat), area Community con sfide e badge punti. Raffinamento futuro: WebSocket al
  posto del polling (latenza percepita più bassa, meno richieste).
- [x] **Push GitHub** — `gh auth login` (SSH) configurato; remoto passato a
  `git@github.com:saulusprime/Scacchi.git`, tutti i commit pubblicati. D'ora in poi il
  push fa parte del workflow di ogni step.

## Motore scacchi

- [x] ⭐ **Abbandono e patta d'accordo** — `POST /sessions/{id}/resign` (vince
  l'avversario; col re nudo → patta, come la bandierina) e `POST .../draw`
  (offer/accept/decline; colonna `draw_offer`, migrazione 0006; la mossa dell'altro
  vale come rifiuto — FIDE 9.1; contro l'IA non disponibile; offerta incrociata =
  accettazione). Regole di fiducia delle mosse (token nei remote); pulsanti 🏳️/½ e
  banner di risposta in partita; `finish_reason="resign"/"agreement"`; guardia
  anti-corsa nel worker IA (refresh dello stato prima di muovere).
- [x] Bandierina fedele all'art. 6.9 — `Chess.cannot_mate(board, color)` (matti
  d'aiuto su base materiale: impossibile solo con re nudo, K+C vs re nudo, o soli
  alfieri monotinta di entrambe le parti; K+2C e ogni caso con pezzi/pedoni avversari
  possono dare matto). Usata da `_winner_on_time` → vale per bandierina E abbandono.

- [x] ⭐ **Avversario Stockfish (NNUE) configurabile** — integrato via protocollo **UCI**
  (`backend/app/opponents/stockfish.py`): tipo di giocatore «Stockfish» al setup partita;
  percorso binario da super admin (`stockfish.path`) o `STOCKFISH_PATH`; forza regolabile
  (*Skill Level* 0–20, `UCI_Elo` 1320–3190, tempo per mossa); ripiego automatico sul motore
  interno se il binario manca.
- [x] Stockfish: **processo persistente** con lock (`_PersistentEngine`) al posto
  dell'avvio one-shot per mossa: handshake una volta, opzioni inviate solo al cambio,
  `ucinewgame` solo a partita nuova (hash calde nelle continuazioni), watchdog +
  **respawn automatico** su crash/cambio percorso; `quit` solo alla chiusura. La
  selezione della forza al setup c'era già (preset Zeus…Pan). Verificato dal vivo:
  un solo PID per tutta la partita, stats nella diagnostica admin.
- [x] Stockfish come **sparring** (`app/sparring.py` + card admin): match a colori
  alternati contro un preset a Elo noto, stima con modello logistico
  (`diff = 400·log10(p/(1−p))`) e margine; un match alla volta, in background.
- [x] **Analisi post-partita** (`app/analysis.py` + pulsante in partita): Stockfish valuta
  ogni posizione (`stockfish.analysis_ms`), errori marcati ??/?/?! con suggerimento del
  motore, grafico dell'andamento; risultato salvato in `analysis_json` (una volta sola).
- [x] **Moviola** (rewind/step-by-step) sulle partite concluse: ⏮◀▶⏭ + clic sul log,
  **note per mossa** salvate nello storico (`moves_json`, visibili anche nella scheda
  giocatore); **export GIF animata** dell'intera partita (Pillow, scacchi/dama/tris/
  forza4; glifi con font di sistema e ripiego a lettere).
- [x] **Patta per triplice ripetizione** — `Chess.is_repetition_draw(history)` (chiave
  FIDE: scacchiera+tratto+arrocco+en passant, storico rigiocato); dichiarata d'ufficio da
  `finish_if_terminal` alla terza occorrenza (`finish_reason="repetition"`), mostrata in
  partita come «(triplice ripetizione)». Da regolamento sarebbe su richiesta: qui è
  automatica per evitare partite infinite.
- [x] **Apertura-bersaglio dal profilo avversario** — l'indice del libro ricorda il nome
  della linea; `opening_move(prefer=…)` filtra le continuazioni sulle `weakest_openings`
  del profilo (aggancio per sottostringa, varianti comprese; nessun aggancio → scelta
  normale). Le porta `opponent_style` → `style["target_openings"]` → dispatcher.
- [x] **Stima delle blunder** — `profile["accuracy"]` aggrega le analisi motore in cache
  (ACPL con tetto 1000 cp/mossa, blunder/errori/imprecisioni del SOLO lato del giocatore);
  `POST /users/{id}/analyze-history` analizza in background le partite non ancora
  analizzate (pulsante nella scheda giocatore). Sotto 20 mosse analizzate la stima non
  tocca debolezze/stile; sopra: blunder frequenti → +aggressività, ACPL alto → debolezza.
- [x] **Libro di aperture più ampio** — 75+ linee con le varianti principali, indicizzato
  **per posizione** (vale anche nelle trasposizioni), estendibile via `CHESS_BOOK_FILE`
  (file di testo `Nome: e2e4 e7e5 …`).
- [x] **Import libro da PGN** — `engine/chess/pgn.py`: parser SAN che rigioca col
  motore (arrocco, catture, disambiguazioni, promozioni; commenti/varianti/NAG puliti);
  `CHESS_BOOK_FILE` accetta ora anche un .pgn (auto-riconosciuto): una linea di libro
  per partita (prefisso di 16 semimosse, nome da Opening/ECO o Bianco–Nero).
- [x] **Formato Polyglot (.bin)** — `engine/chess/polyglot.py`: hash Zobrist con la
  tabella standard (781 costanti, VALIDATE sui 9 vettori ufficiali della specifica:
  arrocchi, en passant condizionale, tratto), probing binario del .bin ordinato,
  scelta pesata, arrocchi «re cattura torre» tradotti in UCI; `CHESS_POLYGLOT_BOOK`
  interrogato quando il libro interno non ha la posizione (il libro con nomi ha
  priorità: mantiene le aperture-bersaglio).
- [x] **Potenziamenti di ricerca** — tutti e quattro: **SEE** (swap con raggi X e
  guardia del re; pota le catture perdenti in quiescence), **PVS** (finestra nulla
  dopo la prima mossa, ai nodi interni E alla radice, composto con la LMR),
  **aspiration windows** alla radice (±50 cp dal punteggio precedente, riaperta sul
  fail), **futility pruning** a depth 1 (statico+150 ≤ alpha → quiete saltate, mai la
  prima legale né gli scacchi). Misurato a profondità 6: −36/−62/−65% di tempo su
  iniziale/mediogioco/tattica, stesse mosse e stessi punteggi.
- [x] **Finali** — *mop-up* (con vantaggio schiacciante: re avversario spinto al bordo
  + re propri avvicinati, pesi 8/5 che dominano il rumore posizionale) e riconoscimento
  **KPK** (regola del quadrato con tempo, pedone di torre in angolo, re davanti al
  pedone; l'euristica SOSTITUISCE la valutazione del finale). Prova funzionale: da
  KQ vs K il motore matta in ~7 mosse a 0,5 s/mossa. Mini-tablebase rimandata (non
  necessaria coi risultati attuali).
- [x] **Pondering** (`app/ponder.py`) — durante il turno dell'umano un thread riempie
  una **TT condivisa per sessione** sulla posizione corrente (niente ponderhit da
  gestire: qualunque replica beneficia dei sottoalberi); la ricerca vera del worker
  la riusa (~3× meno nodi a parità di profondità). Ciclo di vita: start a turno
  umano, stop alla mossa (TT conservata), drop a fine partita; cap 400k voci; solo
  scacchi umano-vs-motore-locale, gate `ponder.enabled` + async.
- [x] **Livelli di difficoltà** selezionabili in partita — cinque preset del MOTORE
  LOCALE (`local.ENGINE_LEVELS`): Maestro (piena forza), Esperto, Medio,
  Apprendista, Novizio; ogni livello calibra tempo di riflessione e **jitter**
  (a jitter alto il motore sceglie anche mosse lontane dalla migliore: errori
  "umani") e **scavalca il provider remoto**. Voci «Motore — …» al setup; stessa
  colonna `*_ai_level` dei preset Stockfish; i livelli depotenziati sono esclusi
  dal pondering; etichetta del livello nell'intestazione della partita.
- [x] **Suggerimento mossa (hint)** — `POST /sessions/{id}/hint` col motore locale a
  budget ridotto (`hints.engine_ms`), per tutti i giochi; **riservato ai principianti**
  (negato oltre `hints.max_wins` vittorie nel gioco), mai nel **formato FIDE** (e nei
  futuri tornei/campionati), col token del giocatore al tratto nei remote; pulsante 💡
  in partita con mossa evidenziata.
- [x] **Export PGN / import FEN** dall'interfaccia — «📄 Esporta PGN» in partita
  (`GET /sessions/{id}/pgn`: tag standard, mosse in SAN dal nuovo scrittore
  `pgn.uci_to_san`/`san_line`, note dei giocatori come commenti `{…}`, tag
  `SetUp`/`FEN` e numerazione `1...` nelle partite da FEN); campo «Posizione
  iniziale FEN» al setup (colonna `start_fen`, migrazione 0007) — validata dal
  motore (re, scacco al lato senza tratto, posizione non conclusa), normalizzata
  con `to_fen`; replay/analisi/commento/Stockfish/ripetizioni ripartono tutti
  dalla FEN (helper unico `stockfish.uci_position`). X resta il Bianco.

## IA e provider remoti

- [x] ⭐ **Concorrenti IA multipli** (Claude, Gemini, Grok, Qwen, OpenAI) — avversari
  **selezionabili al setup della partita** («IA — Claude», «IA — Gemini», … una voce per
  provider, lati con concorrenti diversi possibili), ognuno con la propria
  configurazione/token nella pagina Provider IA; aggiunti **Gemini** (Google) e **Grok**
  (xAI), endpoint OpenAI-compatible. Colonne `x/o_ai_provider` (migrazione 0003).
- [x] **Classifica delle IA e tornei** (`app/ai_arena.py`, pagina «Arena IA») —
  ogni configurazione IA è un'IDENTITÀ (`motore:<livello>`, `stockfish:<preset>`,
  `ai:<provider>`, generici `ai`/`stockfish`) con **rating Elo per gioco**
  (partenza 1500, K=32, tabella `ai_ratings`), aggiornato SOLO su partite
  IA-vs-IA concluse (hook in `finalize_session`; contro gli umani restano i
  punti 3/1/0). **Tornei** round-robin (2-8 identità, singolo o andata/ritorno):
  le partite sono vere sessioni giocate in sequenza da un thread (storico,
  moviola, PGN), con classifica del girone (punti di piattaforma) e pagina di
  dettaglio in auto-aggiornamento. Migrazione 0008; endpoint `/arena/*`.
- [x] **Circuit breaker** sui provider remoti (`app/breaker.py`) — dopo N errori
  consecutivi (default 3, parametro `providers.breaker_failures`) il circuito si
  APRE: chiamate remote saltate per il raffreddamento (`providers.breaker_cooldown_s`,
  default 120s: niente attese di timeout a ogni mossa), poi MEZZO APERTO (la
  prossima chiamata fa da sonda; successo richiude, errore riapre). Scudo unico
  `api_ai.guarded_complete` (mosse + commentatore LLM); «Verifica connessione»
  bypassa e registra (sonda manuale); stato nel payload provider e badge
  «⛔ sospeso» nella pagina Provider IA. Stato in memoria per processo.
- [x] **Cifratura dei token provider** nel DB (`app/token_crypto.py`) — Fernet
  (libreria `cryptography`), formato `enc:…` nella stessa colonna (niente
  migrazione di schema); righe legacy in chiaro cifrate al primo avvio dal seed.
  Chiave: `TOKENS_KEY` in `.env` (consigliata in produzione) o derivata da
  `ADMIN_TOKEN` (PBKDF2); chiave cambiata → token illeggibile = assente, con
  badge «da reinserire» nella pagina Provider IA (mai eccezioni).
- [x] **Cache del profilo avversario** (`app/profile_cache.py`) — una copia per
  giocatore in memoria, consultata da `opponent_style` (ogni mossa dell'IA) e
  dall'endpoint `/users/{id}/chess-profile`. **Invalidazione a eventi** (fine
  partita di scacchi in `finalize_session`, analisi scritta in `analysis`) +
  TTL di sicurezza `profile.cache_ttl_s` (default 300s; 0 = disattivata). Il
  dict è condiviso: trattato come immutabile (i chiamanti copiano).
- [x] **LLM come commentatore + badge di qualità** — `app/commentary.py`: dopo ogni mossa
  di scacchi Stockfish classifica (🌟 da maestro, 👍 buona, ⚔️ aggressiva, 🐔 codarda,
  🤔 imprecisa, 😬 errore, 🤡 blunder; simbolino in alto a destra del pezzo mosso) e il
  provider IA attivo aggiunge una battuta nel widget «🎙️ Commento». Best effort in
  background; interruttori `commentary.enabled` / `commentary.llm`.

## Giochi

- [x] **Dama potenziata** — (1) **priorità FID complete** tra catture di pari
  numero (`_capture_paths` traccia i pezzi presi; cascata in `legal_moves`:
  massimo pezzi → si prende CON la dama → più dame → la linea che incontra
  PRIMA una dama → scelta libera); (2) **patta per triplice ripetizione**
  (`is_repetition_draw`, chiave scacchiera+tratto, dichiarata d'ufficio: chiude
  i finali dama-contro-dama infiniti); (3) **motore dedicato**
  (`draughts/engine.py`: alpha-beta negamax + approfondimento iterativo con
  budget di tempo + **estensione delle catture** contro l'orizzonte + TT +
  jitter riscalato dai livelli, agganciato al dispatch `engine_move` esistente
  al posto del minimax generico a profondità 4); (4) euristica con **trincea**
  e **centro** oltre a materiale e avanzamento.
- [x] **Forza 4**: motore dedicato più profondo — FATTO (2026-07-11):
  `connect4/engine.py` bitboard alla Fhourstones (7 bit/colonna con
  sentinella), negamax + TT con flag (chiave `position+mask`), tattica esatta
  a ogni nodo (vittoria immediata, doppia minaccia, blocco forzato, mai sotto
  una casella vincente avversaria), approfondimento iterativo con budget e
  jitter riscalato; scovato e corretto anche il falso pareggio di radice del
  motore della dama (bound = alpha nel pool del jitter).
- [x] **Backgammon** — nodi del caso realizzati: il server tira i dadi (`resolve_chance`),
  un dado = una mossa, colpi/barra/uscita implementati.
- [x] **Nuovi giochi deterministici — Othello e Gomoku** (2026-07-11): **Othello**
  (8×8, giri in tutte le direzioni, **passo automatico** dentro `apply`, conta
  pedine in `status_line`, minimax generico con euristica posizionale
  angoli+mobilità, tavoliere verde con puntini sulle caselle legali) e **Gomoku**
  (goban 15×15, cinque o più in fila — freestyle, **motore dedicato**
  `gomoku/engine.py`: candidati entro distanza 2 dalle pietre, tattica esatta
  cinquina/blocco/doppia minaccia, valutazione a finestre di 5 con delta
  incrementale, approfondimento iterativo). Dischi/pietre ●○ anche nella GIF;
  celle legali via `legal_moves` nel client (le altre disabilitate). Del gruppo
  originario resta il Filetto 3D (in TODO).

## Istruzione guidata (tutorial) + voce sintetica

- [x] ⭐ **Sistema graduale di istruzione guidata** — realizzato:
  - **Contenuti** in `backend/app/lessons/` (un modulo per gioco, helper `pos8`/`sq` in
    coordinate scacchistiche): corso di scacchi in 7 lezioni (scacchiera → pedone →
    torre/alfiere → cavallo → donna/re → arrocco/en passant → matto del corridoio),
    dama (movimento, presa obbligatoria/multipla, promozione), Tris. Ogni passo: testo +
    posizione preimpostata + evidenziazioni + eventuale mossa richiesta con verifica.
    Guardiano nei test (`validate_lesson`): contenuti malformati non passano.
  - **Progressi per utente** (`lesson_progress`, migrazione 0004): riprendi dal passo
    raggiunto, `completed` definitivo, `last_step` non regredisce; anonimi fruiscono
    senza salvataggio. Endpoint `GET /lessons`, `GET /lessons/{code}`, `POST progress`.
  - **UI** «Impara» (navbar): indice per gioco con badge/riprendi; pagina lezione con la
    STESSA scacchiera di gioco (CSS condiviso `board_css.html`), evidenziazioni,
    clic origine→destinazione verificato, avanti/indietro.
  - **Voce**: pulsante 🔊 + «voce automatica» (localStorage), lettura di ogni passo via
    `/tts` (italiano con Piper).
  - Prossimi passi possibili: lezioni per Forza 4/Backgammon, aperture commentate,
    esercizi con più mosse consecutive e posizioni giocate contro il motore.
- [x] **Servizio TTS nel backend** (`backend/app/tts.py` + `GET /tts` e `GET /tts/status`):
  astrazione multi-motore con import pigri (motore assente → 503 spiegato, il tutorial
  resta testuale), **cache su disco** dei WAV per motore+voce+velocità+frase
  (`backend/tts_cache/`, pubblicazione atomica), un solo thread di sintesi, parametri
  del super admin nella categoria **Voce** (attivazione, lingua di default, voce per
  lingua, velocità, lunghezza massima). Card di stato con anteprime audio nella pagina
  Admin. *Verificato dal vivo: italiano ~1s/frase, cache a ~0,1s.*
- [x] ⚠️ **Lingua — gestione delle lingue del TTS**: scelta l'opzione (a) — **Piper TTS**
  per l'**italiano** (`piper:it_IT-paola-medium`, voce scaricata da HuggingFace al primo
  uso in `backend/tts_voices/`), **KittenTTS** per l'**inglese**
  (`kitten:expr-voice-2-f`). La lingua instrada al motore tramite i parametri
  `tts.voice_it` / `tts.voice_en` (formato `motore:voce`: si può passare l'inglese a
  Piper senza toccare codice; nuova lingua = nuova voce in `LANG_SETTINGS` + parametro).
  ⚖️ Piper (`piper-tts` 1.4.2) è **GPL-3** → dipendenza **opzionale** non inclusa in
  requirements (progetto MIT): si abilita con `make piper` (scelta dell'operatore).

## Piattaforma e gamification

- [x] **Rating Elo** (`app/rating.py`, tabella `ratings`, migrazione 0009) —
  Elo classico con **K adattivo stile FIDE** (40 sotto le 30 partite =
  «provvisorio», 20 fino a 2400, 10 oltre), per (giocatore, gioco, **stagione**).
  Si aggiorna SOLO sulle partite umano-vs-umano (pool pulito: le IA hanno il
  loro pool nell'arena; contro le IA restano i punti 3/1/0, che sopravvivono
  come misura di attività). **Stagioni** dal parametro `elo.season`: cambiarlo
  fa ripartire tutti da 1500, lo storico resta interrogabile
  (`/rankings/elo/{game}?season=`). Classifica Elo nella pagina Classifiche
  (con picco e flag «?» provvisorio) e card «Rating Elo» nella scheda
  giocatore. Bugfix scovato dai test: `score_for` senza flush duplicava la
  riga punti con lo stesso utente su entrambi i lati (autoflush=False).
  Glicko rinviato: il K adattivo copre il caso «nuovo giocatore» senza RD.
- [x] **Tornei umani** — `human_tournaments.py` + `/tournaments` (2026-07-09):
  eliminazione diretta (seed dall'Elo, bye alle teste di serie, accoppiamenti
  classici, patta → passa il Nero/draw odds) e girone all'italiana (anche
  andata/ritorno). Partite = vere sessioni in «le mie partite»; avanzamento
  automatico via hook in `finalize_session`; pagina con tabellone a colonne.
  Tornei riservabili a un gruppo.
- [x] **Gruppi — gestione** (2026-07-09): ruoli founder/admin/member (solo il
  founder li cambia), inviti con accettazione dell'invitato (re-invito riusa
  la riga), espulsioni/uscita con permessi graduati, classifica interna per
  gioco (punti+Elo) o complessiva. Scheda gruppo nel frontend + banner inviti.
- [x] **Sfide gruppo-vs-gruppo** (2026-07-09, `group_matches.py` +
  `/group-matches`, migr. 0013): squadre a tavoliere multiplo (1-8) — propone
  e risponde un manager; formazioni AUTOMATICHE per Elo (tavolo 1 = il più
  forte, membri comuni ai due gruppi esclusi), colori alternati per tavolo,
  1/½ punti a tavolo, parità legittima; verdetto e notifiche al termine di
  tutti i tavoli (hook in finalize_session). Bilancio V/N/P nella scheda
  gruppo, pagina della sfida coi tavolieri. Le sessioni sono remote=True:
  ogni mossa vuole il token di chi muove.
- [x] **Spettatori e replay animato** (2026-07-09): `GET /community/live`
  (solo partite a distanza — le azioni vogliono il token, lo spettatore non
  interferisce — e IA-vs-IA; hotseat escluse) + pagina spettatore
  `/partite/<id>/guarda/` in sola lettura: in diretta fa polling dello stato
  (orologio, dadi, ultima mossa evidenziata), a partita finita diventa il
  replay animato (play/pausa/velocità/slider sui fotogrammi di `/replay`,
  endpoint che esisteva già). Sezione «Partite in diretta» in Community e
  link «Replay animato» fra gli export post-partita.
- [x] **Notifiche/inviti a giocare** (2026-07-09): sfide come INVITI
  (`/challenges`, migr. 0012) — lo sfidante sceglie gioco/lato/cadenza
  (validata subito), lo sfidato accetta (nasce la partita a distanza con
  orologio) o rifiuta; notifiche persistenti (`notifications.py`, testo
  composto alla lettura da kind+parametri, bilingue) con campanella 🔔 in
  navbar via heartbeat; campanelle anche per inviti di gruppo, nuovo turno
  di torneo e fine torneo. Aprire Community segna le notifiche come lette;
  le lette oltre 50 vengono potate.

## Frontend / UX

- [x] **Riorganizzazione frontend — Fase 1: Navigazione** (2026-07-11, modello
  chess.com): navbar a **5 aree** (Gioca ▾, Puzzle, Impara, Guarda ▾,
  Community ▾) con menu a discesa "disclosure" accessibili (bottone ▾ con
  `aria-expanded`, Esc e click-fuori chiudono, hover solo coi mouse veri);
  su mobile **hamburger ☰** con aree impilate e menu in linea; **menu profilo
  sull'avatar** (scheda, statistiche, Admin — non più voce di primo livello —
  ed esci); **campanella 🔔 col pannello notifiche** (endpoint nuovo
  `notifiche.json` con URL risolti lato server + `notifiche/lette.json`;
  aprire il pannello segna lette, badge solo col non-letto); ancore di
  sezione in community.html (#online #dirette #sfide #notifiche #partite)
  come bersagli dei menu finché gli hub non esistono. URL invariati,
  heartbeat conservato, voci nuove tradotte.
- [x] **Riorganizzazione frontend — Fase 2: Hub «Gioca»** (2026-07-11):
  `/gioca/` è la LANDING dell'area (vista `play_hub` + play_hub.html) con le
  azioni (nuova partita, tornei, registra), «Le tue partite in corso» (riprendi,
  con «Tocca a te!»), «Sfide in attesa» (accetta/rifiuta/ritira — stessi POST
  della community) e «Tornei aperti» (primi 6 open/running + link a tutti);
  il setup si è spostato su `/gioca/nuova/` MANTENENDO il nome di rotta
  `play_setup` (tutti i reverse seguono da soli); le sottovoci del menu Gioca
  puntano alle sezioni dell'hub; `challenge_action` ora torna all'hub.
  Trappola verbalizzata: i mock nei test devono rispecchiare la FORMA vera
  del payload (`/tournaments` risponde `{"tournaments": []}`, non una lista —
  il baco l'ha scovato la verifica dal vivo, non i test).
- [x] **Riorganizzazione frontend — Fase 3: Hub «Guarda»** (2026-07-11):
  `/guarda/` è la landing dell'area (vista `watch_hub` + watch_hub.html) con
  «Partite in diretta» (auto-aggiornate dal polling di community.json),
  «Tornei dell'Arena IA» (primi 6, con avanzamento partite) e «Replay
  recenti» — endpoint backend NUOVO `GET /community/recent` (ultime 10
  concluse della stessa platea delle dirette: a distanza o IA-vs-IA, con
  esito 1–0/0–1/½–½); helper `_side_label` e filtro `_WATCHABLE` condivisi
  fra live e recent. Menu «Guarda»: Dirette e Replay puntano alle sezioni
  dell'hub, Arena IA è la sottopagina.
- [x] **Riorganizzazione frontend — Fase 4: Community ristretta** (2026-07-11):
  la pagina Community è la landing d'area — giocatori ONLINE (col polling e la
  Sfida) + rimandi a Giocatori/Gruppi/Classifiche + riga che indirizza a
  Guarda/Gioca; le sezioni storiche sono SMEMBRATE (dirette → hub Guarda,
  sfide e partite in corso → hub Gioca, notifiche → campanella e nuova pagina
  `/notifiche/` che elenca tutto e segna letto all'apertura — è il bersaglio
  di «Tutte le notifiche»); `community.json` snellito (via `my_games`: una
  query in meno a ogni heartbeat); `challenge_new` reindirizza all'hub Gioca.
- [x] **Riorganizzazione frontend — Fase 5: Home cruscotto** (2026-07-11, la
  riorganizzazione sul modello chess.com è COMPLETA): per il LOGGATO la home
  è il cruscotto personale — saluto con alias, azioni rapide (nuova partita,
  puzzle, Guarda), banner sfide in attesa e notifiche non lette coi link,
  «Le tue partite in corso» (riprendi con «Tocca a te!») e le dirette in
  evidenza; per l'ANONIMO resta la vetrina con la registrazione. Verificata
  dal vivo con LOGIN REALE (utente demo creato e approvato via API, client
  Django, screenshot del cruscotto con dati veri). MANUAL aggiornato con la
  sezione «Navigazione ad aree».
- [x] **Riorganizzazione frontend — rifiniture** (2026-07-11, l'intera sezione
  è CHIUSA): **ricerca giocatore in navbar** (`role="search"` → `/giocatori/?q=`,
  filtro per alias o nome; UN solo risultato → dritti alla scheda; feedback
  «Risultati per …» con link a tutti) e **breadcrumb d'area** su 18 sottopagine
  (blocco `breadcrumb` + stile `.crumbs` in base.html: Gioca › Tornei,
  Community › Giocatori › alias, Guarda › Arena IA, Impara › lezione,
  Puzzle › #id, …); il link di uscita dello spettatore va a «Guarda» (non più
  alla Community).

- [x] **Promozione con dialog grafico** — pannello sopra la scacchiera coi
  quattro pezzi cliccabili nei colori del TEMA del lato che muove (♛♜♝♞, classi
  `.cell` riusate); click fuori o Esc ANNULLA la mossa (deseleziona), tasti
  q/r/b/n da tastiera; `choosePromotion` è ora una Promise (chiamanti click e
  drag&drop adeguati); nella dama più percorsi sulla stessa destinazione NON
  aprono il dialog (equivalenti FID: si gioca il primo, come prima).
- [x] **Scacchiera migliore** — (1) **drag&drop** coi pointer events (tap
  origine→destinazione intatto; ghost del pezzo, promozione al rilascio, click
  post-drop soppresso, `touch-action:none` nella cornice); (2) **ultima mossa
  evidenziata** (velo dorato su origine/destinazione — negli scacchi; percorso
  intero nella dama — anche in moviola sulla semimossa corrente);
  (3) **orientamento dal lato del Nero**: auto per il Nero remoto + pulsante
  «🔄 Ruota» — il DOM resta in ordine di scacchiera, ruota solo la CSS `order`
  (flyer/badge/indici intatti), coordinate della cornice che seguono la vista;
  (4) coordinate già nella cornice da torneo; (5) **pezzi catturati** sotto la
  scacchiera con bilancio materiale (+n; dama: conteggio pedine; nascosto nelle
  partite da FEN, corredo non standard).
- [x] **Responsive mobile** — media query globali in base.html (spazi compatti,
  nav fitta ma completa, TABELLE SCORREVOLI in orizzontale, input ≥16px anti-zoom
  iOS); **`fitCellPx` condiviso** in board_css.html: la casella si restringe per
  far entrare scacchiera+cornice nello schermo (play e lezioni); in partita la
  scacchiera si RIMISURA al resize/rotazione (debounce 200ms, mai a metà di un
  drag); cornice sottile sotto i 480px (coordinate conservate); log mosse e
  colonna laterale impilati su telefono. Il drag&drop era già touch (pointer
  events + touch-action:none).
- [x] **Accessibilità dei giochi** — le caselle (già `<button>`) hanno
  **etichette ARIA** «coordinata + pezzo» localizzate («e4, pedone bianco»;
  backgammon col conteggio; aggiornate a ogni render), **roving tabindex** con
  frecce direzionali che seguono la VISTA (rotazione compresa; nella dama
  saltano le case chiare non giocabili), Invio/Spazio nativi; `aria-live` su
  turno/stato/hint/spiegazione, `role="alert"` sull'offerta di patta; dialog di
  promozione con `role="dialog"`/`aria-modal` e fuoco sul primo pezzo;
  `focus-visible` interno sulle caselle; etichette sui bottoni-icona (moviola,
  colonne del Forza 4); nav con `aria-label`.
- [x] **i18n (prima tranche)** — infrastruttura Django completa
  (LocaleMiddleware, LANGUAGES it/en, LOCALE_PATHS, rotta `set_language`,
  **selettore lingua in navbar**); stringhe marcate: navbar, pagina di gioco
  (template + TUTTO il JS via dizionario `ui` costruito nella view con gettext
  → `json_script`), label di tutti i form; catalogo **inglese completo**
  (67 stringhe, .po+.mo in `frontend/locale/`). Restano da marcare le pagine
  secondarie (home, community, arena, admin, lezioni — contenuti inclusi) e i
  messaggi del backend: v. voce sotto.
- [x] **i18n (seconda tranche)** — TUTTI i template rimanenti marcati (home,
  community, arena+torneo, classifiche, giocatori/scheda, gruppi, admin,
  admin IA, lezioni indice+player, form, batch), JS incluso (polling della
  community e del torneo, feedback delle lezioni — stringhe rese dal template);
  catalogo EN completo: ~170 msgid tradotti, voci FUZZY di msgmerge corrette a
  mano (una «No»→«First name» inclusa), .mo compilato; smoke test su 12 pagine
  IT/EN. L'interfaccia è ora interamente bilingue.
- [x] **i18n (dati)** — i18n lato BACKEND (`app/i18n.py`): middleware FastAPI
  che legge Accept-Language → ContextVar; `_()` traduce alla RISPOSTA (il DB
  resta in italiano, lingua sorgente) con **catalogo a dizionario**
  (`catalog_en.py`, 208 voci — scelto sul gettext/babel: una sola lingua
  target, tutto greppabile, fallback = sorgente). Tradotti: ~76 messaggi
  d'errore dei router (f-string → `_(template).format`), motivi/consiglio del
  tilt, etichette dei parametri admin (get_all), **90 nomi di aperture**
  (nomenclatura inglese standard, tradotti nella vista), profilo scacchistico
  alla FRONTIERA (la cache condivisa resta italiana; debolezze parametrizzate
  ricomposte via regex coi numeri preservati). Il frontend inoltra la lingua
  attiva su ogni chiamata (`api_client` → Accept-Language). Trappola evitata:
  `for _ in range(...)` ombreggiava la funzione di traduzione.

## Sicurezza / DevOps

- [x] **Tipizzazione SQLAlchemy 2.0** — `Base(DeclarativeBase)` e TUTTI i
  modelli in stile `Mapped[]`/`mapped_column` (relazioni comprese:
  `Mapped[list[...]]`, `Mapped[User | None]` con foreign_keys). Tipi SQL
  espliciti conservati; nullabilità resa fedele nelle annotazioni, comprese le
  colonne nullable «per omissione» (created_at & co.). Prova di identità dello
  schema: **`alembic check` → nessuna operazione** (nessuna migrazione
  generata). 253 test verdi.
- [x] **CI GitHub Actions** (2026-07-09): pipeline completa al posto di quella
  «tollerante» dell'era doc-only — checkout con submodule KittenTTS (il
  requirements lo installa dalla root), stockfish+gettext da apt, ruff
  check+format, msgfmt sul catalogo .po, `alembic upgrade head`+`check` su DB
  vergine (parità migrazioni/modelli) e pytest completo. Coverage rimandata
  (la suite è già il gate; il numero arriverà con un badge quando servirà).
- [x] **Mossa IA: coda di lavoro** (`app/jobqueue.py`) — pool di worker
  LIMITATO (`ai.workers`, default 2) al posto del thread-per-sessione: N
  partite IA non aprono più N motori in concorrenza, le eccedenti aspettano.
  Enqueue idempotente (il polling non duplica), **ripresa al riavvio**
  (`recovery_scan` al lifespan: le partite al turno dell'IA ripartono da sole —
  prima restavano ferme finché un client non le guardava), introspezione
  `GET /admin/jobs` (worker/code/contatori). **RabbitMQ valutato e scartato**:
  il DB è già lo stato durevole dei job (una sessione in_progress col tratto
  all'IA È il job; un broker sarebbe una seconda fonte di verità), footprint
  operativo ingiustificato su processo singolo+SQLite; a più processi/host la
  strada naturale è Postgres SKIP LOCKED o Redis/RQ dietro la STESSA
  interfaccia (enqueue/snapshot restano, cambia il trasporto).

## Già completati (storico recente)

- [x] Motore scacchi dedicato (alpha-beta, quiescence, TT, null-move, LMR) — vedi HANDOFF.
- [x] Modello dell'avversario (schemi/debolezze dallo storico) + stile IA adattivo.
- [x] Provider IA configurabili da super admin (token in DB, mai esposti dall'API).
- [x] Parametri di programma centralizzati + interfaccia super admin.
- [x] Confronto `ADMIN_TOKEN` in tempo costante; budget IA-vs-IA limitato.

## Statistiche avanzate del giocatore (idee da chess.com «Insights», 2026-07-07)

- [x] ⭐ **Pagina «Statistiche avanzate»** (`/giocatori/<id>/statistiche/`,
  `app/insights.py`, `GET /users/{id}/insights`) — per gioco: punti, Elo
  (stagione corrente), V/P/S, **serie di vittorie** (migliore e in corso);
  scacchi in profondità: rendimento per colore, precisione (ACPL/blunder dalla
  cache), **distribuzione degli esiti** (matto/tempo/abbandono/accordo/
  ripetizione), conteggio dei badge di qualità sulle proprie mosse. Solo
  materia prima già in cache, mai lavoro del motore. Bilingue IT/EN.
- [x] **Raccolta «mosse geniali»** (prima versione) — galleria nella pagina
  Statistiche: le proprie mosse col badge 🌟 con **screenshot della posizione**
  (`GET /sessions/{id}/board.png?ply=N`, renderer Pillow della GIF riusato,
  cache 1h), avversario (alias umano o etichetta del concorrente IA), esito,
  data e link alla partita/moviola (`insights.brilliancies`).
- [x] Raccolta mosse geniali — raffinamenti: (1) **badge 💎 «geniale
  (sacrificio)»** — mossa quasi-ottimale (perdita ≤30cp) che OFFRE materiale:
  `commentary._is_sacrifice` rigioca la mossa col motore puro e misura con la
  **SEE** quanto l'avversario vince catturando il pezzo appena mosso (soglia ≥2
  pedoni netti; prudente su ogni dubbio); (2) **filtri della galleria** per
  tipo (💎/🌟) e per pezzo (campo `piece` dalle notazioni, arrocco = Re);
  (3) **salto della moviola** esattamente alla semimossa (`?ply=N` nell'URL
  della partita, usato dai link della raccolta). 💎 è di prima classe in
  insights (BRILLIANT, badges, conteggio).
- [x] **Prestazioni per cadenza** — `insights.by_cadence`: per ognuna fra
  senza-orologio/blitz/rapid/classical/FIDE (ordine fisso, solo cadenze
  giocate): partite, V/P/S, quante analizzate e **ACPL delle proprie mosse**
  (— dove l'analisi manca). Tabella nella pagina Statistiche avanzate,
  bilingue. Trappola .po documentata: riempire `msgstr ""` di un'entry
  MULTIRIGA con un regex a riga singola concatena traduzioni fantasma.
- [x] **Valutazione per i quattro aspetti del gioco** — `insights._aspects`
  (2026-07-09): aperture = ACPL prime ~12 mosse + aderenza al libro (pesa ¼);
  tattica = blunder commessi + blunder avversari puniti (risposta < 100 cp);
  strategia = ACPL delle mosse quiete del mediogioco; finali = ACPL con ≤ 6
  pezzi non-pedone. Fasi dal replay deterministico (`_phases`, nessuna
  ricerca); punteggi 0-100 euristici, None sotto i campioni minimi. Quattro
  riquadri con barre nella pagina Statistiche avanzate, bilingue.
- [x] **Sottocategorie tattiche** (2026-07-11, `tactics.subcategories` dentro
  `insights._aspects`): per ogni mossa che concede ≥250 cp — **matti mancati**
  (|cp| ≥ 9901 prima, non più dopo; classificati per primi), **pezzi in
  presa** (risposta reale = cattura; taglie leggero/torre/donna dalla
  perdita), **scacchi concessi** (risposta di scacco puro), **tattiche
  silenziose** (confutazione quieta) e — trasversale — **catture avvelenate**
  (la mossa concedente era una cattura). Riga «Dettaglio tattico» sotto i
  quattro aspetti, bilingue.
- [x] **Confronto con i pari fascia** (2026-07-11, `insights.peer_comparison`):
  fascia Elo di 200 punti dal rating stagionale (1500 per i non classificati),
  metriche economiche per tutti in un passaggio solo (ACPL e blunder/partita,
  niente replay per i pari), `better_than` = quota di pari fascia strettamente
  peggiori; percentile solo con ≥3 pari da ≥20 mosse analizzate (sotto, grezzi
  e media di fascia con avviso). Tabella «Confronto coi pari fascia» nelle
  Statistiche. La «massa di giocatori» resta il fattore limitante: il codice
  è pronto, il campione crescerà da solo.

## Visione — coaching, community e creator

### Primitive (prerequisiti condivisi)

- [x] ⭐ **Sistema PUZZLE** (`app/puzzles.py`, tabelle `puzzles` +
  `puzzle_attempts`, migrazione 0010) — FEN + **linea di soluzione UCI**
  (solutore agli indici pari, risposte forzate ai dispari), tema e difficoltà.
  **Seed autoriale verificato** (5 matti in 1, controllati col motore
  all'inserimento; idempotente per FEN) + **generazione automatica dai
  blunder** delle partite analizzate (posizione dopo il «??» → confutazione
  del motore locale a 0,8s; temi matto/colpo vincente/punisci l'errore;
  dedup per partita+semimossa). Verifica STATELESS dei tentativi con **matto
  alternativo accettato**; progressi per utente (tentativi/risolto) con token,
  giocabile anche da anonimi. Pagina «Puzzle» in navbar (filtri tema, pulsante
  «genera dai tuoi errori») + player click-click sulla scacchiera condivisa.
  Bilingue IT/EN. → Sbloccati: tilt-breaker, Gatekeeper, Puzzle Story.
- [x] **Rating Elo** — FATTO (v. sezione gamification: `rating.py`, stagioni,
  K FIDE): il prerequisito di «partita classificata» e matchmaking è pronto.

### AI Coach «umano» e psicologico ⭐

- [x] **«Spiegami questa mossa»** — pulsante 🎓 in moviola →
  `POST /sessions/{id}/explain`: l'LLM spiega in ≤3 frasi con i dati GIÀ prodotti
  (FEN prima della mossa, valutazione/perdita/best dall'analisi, badge, apertura,
  nota del giocatore). Passa da `guarded_complete` (circuit breaker); spiegazione
  **salvata nello storico della mossa** (secondo clic senza LLM, ricompare
  navigando la moviola); interruttore `coach.explain_enabled`.
- [x] **Riconoscimento del tilt** (`app/tilt.py`, `GET /users/{id}/tilt`) — due
  segnali dai dati esistenti: N **sconfitte rapide consecutive** (`tilt.losses`,
  `tilt.quick_plies`) e serie di sconfitte con **ACPL recente sopra la propria
  media** × `tilt.acpl_factor` (ultime 3 analisi vs `accuracy.acpl` del profilo).
  Risposta: banner SOFT nel setup con esercizio consigliato (lezioni «Impara»);
  il **blocco** delle nuove partite di scacchi esiste solo come opzione admin
  (`tilt.block`, raffreddamento `tilt.block_cooldown_min` dall'ultima sconfitta,
  mai sulle partite in corso).
- [x] **Bias cognitivi (pattern misurabili)** — `profile["biases"]`
  (`chess_profile._biases`): **donna precoce** (nelle prime 5 mosse proprie),
  **re in centro** (arrocco assente/oltre la 15ª in partite ≥20 semimosse),
  **coazione alla cattura** (maggioranza dei blunder dell'analisi = catture),
  **monotonia in apertura** (≥4 delle prime 8 mosse con lo stesso tipo di pezzo,
  pedoni esclusi). Soglie: ≥5 partite, ≥40% di ricorrenza (≥3 blunder per le
  catture); mostrati nella scheda giocatore. Il confronto con database di
  partite di GM resta fase di ricerca (non implementato).
