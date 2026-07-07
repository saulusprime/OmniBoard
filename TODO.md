# TODO — Idee di potenziamento e miglioramento

> Backlog vivo del progetto: idee raccolte durante lo sviluppo, in ordine sparso dentro
> ogni categoria. Quando un punto viene realizzato, spuntarlo qui e documentarlo in
> [HANDOFF.md](./HANDOFF.md). Le voci con ⭐ sono quelle a maggior impatto percepito.

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
- [ ] **Finali**: euristica "mop-up" (spingere il re avversario al bordo con materiale di
  vantaggio), riconoscimento KPK; eventuale mini-tablebase.
- [ ] **Pondering** — pensare durante il tempo dell'avversario (richiede la mossa async).
- [ ] **Livelli di difficoltà** selezionabili in partita (tempo/profondità/jitter più alto
  per i principianti), oltre al parametro globale `ai.engine_ms`.
- [x] **Suggerimento mossa (hint)** — `POST /sessions/{id}/hint` col motore locale a
  budget ridotto (`hints.engine_ms`), per tutti i giochi; **riservato ai principianti**
  (negato oltre `hints.max_wins` vittorie nel gioco), mai nel **formato FIDE** (e nei
  futuri tornei/campionati), col token del giocatore al tratto nei remote; pulsante 💡
  in partita con mossa evidenziata.
- [ ] **Export PGN / import FEN** dall'interfaccia.

## IA e provider remoti

- [x] ⭐ **Concorrenti IA multipli** (Claude, Gemini, Grok, Qwen, OpenAI) — avversari
  **selezionabili al setup della partita** («IA — Claude», «IA — Gemini», … una voce per
  provider, lati con concorrenti diversi possibili), ognuno con la propria
  configurazione/token nella pagina Provider IA; aggiunti **Gemini** (Google) e **Grok**
  (xAI), endpoint OpenAI-compatible. Colonne `x/o_ai_provider` (migrazione 0003).
- [ ] **Classifica delle IA e tornei** — profilo e punteggi per concorrente IA (quale IA
  gioca meglio?), tornei IA-vs-IA fra provider diversi; oggi i punteggi esistono solo per
  i giocatori umani.
- [ ] **Circuit breaker** sui provider remoti: dopo N errori consecutivi disattivazione
  temporanea automatica (oggi c'è solo il connect-timeout breve).
- [ ] **Cifratura dei token provider** nel DB (oggi in chiaro, scaffold di sviluppo) o
  spostamento in un secret manager.
- [ ] **Cache del profilo avversario** con TTL (oggi ricostruito a ogni mossa umana).
- [x] **LLM come commentatore + badge di qualità** — `app/commentary.py`: dopo ogni mossa
  di scacchi Stockfish classifica (🌟 da maestro, 👍 buona, ⚔️ aggressiva, 🐔 codarda,
  🤔 imprecisa, 😬 errore, 🤡 blunder; simbolino in alto a destra del pezzo mosso) e il
  provider IA attivo aggiunge una battuta nel widget «🎙️ Commento». Best effort in
  background; interruttori `commentary.enabled` / `commentary.llm`.

## Giochi

- [ ] **Dama**: priorità FID fini tra catture di pari numero (preferire la dama, catturare
  più dame, prima le dame); patte per ripetizione.
- [ ] **Forza 4**: motore dedicato più profondo (bitboard + tabella trasposizioni).
- [ ] **Nuovi giochi deterministici**: Othello/Reversi, Filetto 3D, Gomoku.
- [x] **Backgammon** — nodi del caso realizzati: il server tira i dadi (`resolve_chance`),
  un dado = una mossa, colpi/barra/uscita implementati.
- [ ] Backgammon: affinamenti — tiro iniziale "un dado a testa", regola del dado
  maggiore obbligatorio, cubo del raddoppio, punteggi gammon/backgammon, IA
  expectiminimax (oggi greedy dado per dado).
- [ ] **Ludo** (nodi del caso, come il backgammon).

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

- [ ] **Rating Elo/Glicko** al posto dello schema punti provvisorio (3/1/0); stagioni.
- [ ] **Tornei** — eliminazione diretta e gironi, con tabellone.
- [ ] **Gruppi**: ruoli (admin/membro), inviti, espulsioni; classifiche per gruppo;
  sfide gruppo-vs-gruppo.
- [ ] **Spettatori** delle partite live e **replay animato** dallo storico mosse.
- [ ] **Notifiche/inviti a giocare** tra utenti.

## Frontend / UX

- [ ] **Promozione con dialog grafico** (oggi `window.prompt`).
- [ ] **Scacchiera migliore**: drag&drop, evidenzia ultima mossa, orientamento dal lato del
  Nero, coordinate, pezzi catturati a lato.
- [ ] **Responsive mobile** e accessibilità (navigazione da tastiera, ARIA).
- [ ] **i18n** — testi in file di traduzione (oggi tutto hardcoded in italiano).

## Sicurezza / DevOps

- [ ] **Tipizzazione SQLAlchemy 2.0** (`Mapped[]`/`mapped_column`) nei modelli: zittisce i
  falsi positivi di mypy sugli attributi `Column[...]` (il progetto linta con ruff).
- [ ] **Rate limiting** sulle API pubbliche; configurazione **CORS** esplicita.
- [ ] **Audit log** delle operazioni super admin.
- [ ] **CI GitHub Actions**: verificare che il workflow esegua davvero ruff+pytest sul
  codice attuale (nato in fase doc-only); aggiungere coverage.
- [ ] **Docker Compose** (backend + frontend + PostgreSQL) per sviluppo e deploy.
- [ ] **Mossa IA**: coda di lavoro vera (es. worker dedicato) se si passa a più processi —
  l'attuale scheduling in-process presuppone un singolo worker.

## Già completati (storico recente)

- [x] Motore scacchi dedicato (alpha-beta, quiescence, TT, null-move, LMR) — vedi HANDOFF.
- [x] Modello dell'avversario (schemi/debolezze dallo storico) + stile IA adattivo.
- [x] Provider IA configurabili da super admin (token in DB, mai esposti dall'API).
- [x] Parametri di programma centralizzati + interfaccia super admin.
- [x] Confronto `ADMIN_TOKEN` in tempo costante; budget IA-vs-IA limitato.


## Statistiche avanzate del giocatore (idee da chess.com «Insights», 2026-07-07)

> Fonte studiata: chess.com/it/news/view/annuncio-statistiche-avanzate (funzione
> premium «Diamond»; da noi sarebbe GRATIS). Materia prima già in casa: analisi in
> cache (`analysis_json`), badge di qualità per mossa (`moves_json.quality`),
> `profile["accuracy"]`, `tc_category` sulle sessioni. Più partite analizzate =
> insights più ricchi (sinergia col pulsante «Analizza lo storico»).

- [ ] ⭐ **Pagina «Statistiche avanzate»** del giocatore: aggrega le analisi già in
  cache in un cruscotto dedicato (oggi il profilo mostra solo il riassunto).
- [ ] **Raccolta «mosse geniali»**: tutte le mosse migliori giocate (badge 🌟) in un
  archivio consultabile, ognuna linkata alla MOVIOLA sulla posizione esatta; filtri
  per pezzo/tema (es. «sacrifici di torre»). Prerequisito: nuovo badge 💎 «geniale»
  (mossa migliore del motore CHE sacrifica materiale — oggi 🌟 non distingue i
  sacrifici).
- [ ] **Prestazioni per cadenza**: rendimento e precisione separati per
  blitz/rapid/classical/FIDE (`tc_category` già persistita per sessione).
- [ ] **Valutazione per i quattro aspetti del gioco** — aperture, tattica, strategia,
  finali — calcolabile dalle analisi per fasce di semimosse: aperture = ACPL nelle
  prime ~12 + rendimento col libro; finali = ACPL da soglia di materiale; tattica =
  blunder concessi/puniti; strategia = ACPL nelle mosse "quiete" centrali.
- [ ] **Sottocategorie tattiche**: matti mancati (il motore vedeva `mate` e la mossa
  giocata non lo dà — dato già in `evaluate()`), pezzi lasciati in presa (perdita ≥
  valore del pezzo), tipi di tattiche concesse.
- [ ] **Confronto con i pari fascia**: ogni metrica contestualizzata sui giocatori
  della stessa fascia («meglio del 70% dei 1400-1600»). Prerequisito: **rating Elo**
  (già in backlog) + massa di giocatori.
- [ ] **Punteggio aggregato per categoria con peso alla recency**: le partite recenti
  contano più delle vecchie (decadimento esponenziale), come i rating.

## Visione — coaching, community e creator (idee del 2026-07-06, con valutazione)

> Sei proposte analizzate e ordinate per rapporto valore/sforzo. Prima le **primitive
> trasversali** che le sbloccano quasi tutte: costruite quelle, il resto è assemblaggio.

### Primitive mancanti (prerequisiti condivisi)

- [ ] ⭐ **Sistema PUZZLE** (posizione + soluzione + verifica col motore, tag per
  apertura/tema, generazione anche automatica dai blunder delle partite analizzate) —
  sblocca: tilt-breaker (coach), Gatekeeper (repertoire), Puzzle Story (UGC).
  Nota: il PLAYER esiste già — il motore del tutorial (`lessons/`) è di fatto un
  lettore di puzzle a passi; manca la primitiva dati + l'esecuzione libera.
- [ ] **Valuta virtuale** (guadagnata con puzzle/partite/lezioni; mai convertibile in
  denaro) — serve a: pronostici watch party, ricompense creator, mentorship.
- [ ] **Presenza spettatori per partita** (chi sta guardando la sessione N; riusa
  l'infrastruttura heartbeat della community) — serve a: watch party, heatmap, OBS.
- [ ] **Rating Elo** (già in backlog) — prerequisito di «partita classificata»
  (Gatekeeper) e del matchmaking (blocco/suggerimento tilt).

### 1. AI Coach «umano» e psicologico ⭐ (il più vicino a ciò che abbiamo)

- [ ] **«Spiegami questa mossa»**: pulsante in moviola/analisi → LLM spiega in parole
  semplici usando dati GIÀ prodotti (valutazione, mossa migliore, apertura, badge).
  Basso sforzo: prompt su `api_ai._complete`, il modello spiega e non gioca.
- [ ] **Riconoscimento del tilt**: N sconfitte rapide consecutive + ACPL sopra la
  propria media (dati del profilo già esistenti) → avviso + esercizio consigliato.
  ⚠️ Design: blocco SOFT di default (l'obbligo fa scappare i giocatori); versione
  forzata solo come opzione admin.
- [ ] **Bias cognitivi** (attacchi prematuri, ecc.): richiede classificazione di
  pattern sullo storico e un database di partite di GM che NON abbiamo → fase di
  ricerca, non feature immediata.

### 2. Repertoire dinamico e «Gatekeeper»

- [ ] Statistiche per variante già nel profilo (rendimento per apertura): esporre il
  «tracciatore di debolezze» con soglie e trend.
- [ ] **Gatekeeper**: puzzle mirati sulla linea debole come prerequisito per usarla in
  partita classificata. Dipende da: sistema puzzle + Elo. ⚠️ Design: **opt-in**
  («modalità allenatore severo»), mai default — lo studio come punizione allontana
  proprio i principianti.

### 3. Social & Community 2.0

- [ ] **Guerre tra clan / mappa dei territori**: punti influenza da vittorie/puzzle,
  territori in tempo reale. ⚠️ Richiede massa critica (con pochi utenti = territori
  vuoti percepiti come piattaforma morta) + ruoli/inviti nei gruppi (già in backlog).
  Rimandare finché la community non è viva.
- [ ] **Mentorship marketplace** (sessioni 15′ con lavagna e voce): il pezzo più
  costoso della lista — WebRTC, scheduling, valuta. Ultimo della fila.

### 4. Watch party e spettatori

- [ ] **Heatmap dei clic** degli spettatori + sondaggio «che mossa giocherà?» (riusa
  polling + presenza per partita).
- [ ] **Pronostici in valuta virtuale** («patta», «sacrificio entro 10 mosse», …) con
  classifica dei pronosticatori. ⚠️ Lessico: «pronostici», MAI «scommesse»; nessuna
  conversione in denaro.

### 5. User-Generated Content ⭐ (miglior rapporto valore/sforzo dopo il coach)

- [ ] **Editor di Puzzle Story no-code**: composizione di posizioni + mosse richieste
  con verifica; il PLAYER è il motore del tutorial esistente. Servono: persistenza su
  DB (le lezioni oggi sono codice), validazione (`validate_lesson` c'è già),
  pubblicazione + moderazione.
- [ ] **Ricompense creator**: badge speciale, visibilità in home, valuta virtuale
  (niente ad-revenue: non abbiamo pubblicità).

### 6. Integrazione streaming (Twitch/OBS)

- [ ] Primo passo riusabile: **API pubblica documentata** (serve comunque a widget e
  overlay).
- [ ] Overlay OBS con statistiche live; **modalità streamer-vs-chat** (voto della chat
  ogni N mosse). ⚠️ Dipende da API di terzi (Twitch OAuth/chat) e ha valore solo con
  streamer reali interessati: in fondo alla coda.

**Ordine consigliato:** Puzzle → AI Coach (spiegami + tilt soft) → Editor Puzzle Story
→ Valuta virtuale → Watch party → Clan wars → OBS.
