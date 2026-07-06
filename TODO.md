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

- [x] ⭐ **Avversario Stockfish (NNUE) configurabile** — integrato via protocollo **UCI**
  (`backend/app/opponents/stockfish.py`): tipo di giocatore «Stockfish» al setup partita;
  percorso binario da super admin (`stockfish.path`) o `STOCKFISH_PATH`; forza regolabile
  (*Skill Level* 0–20, `UCI_Elo` 1320–3190, tempo per mossa); ripiego automatico sul motore
  interno se il binario manca.
- [ ] Stockfish: **processo persistente** con lock al posto dell'avvio one-shot per mossa
  (risparmia ~100ms/mossa); selezione della forza **al setup della partita** (oggi è un
  parametro globale del super admin); usarlo come sparring per misurare l'Elo del motore
  interno e per l'analisi post-partita.
- [ ] **Patta per triplice ripetizione** dichiarata dalle regole del gioco (il motore la
  evita in ricerca, ma la partita non termina mai per ripetizione).
- [ ] **Apertura-bersaglio dal profilo avversario** — scegliere dal libro le linee in cui
  l'avversario storicamente rende peggio (`weakest_openings` già calcolate).
- [ ] **Stima delle blunder** — rianalizzare col motore un campione di posizioni dello
  storico dell'avversario per quantificare gli errori (profilo più ricco e affidabile).
- [x] **Libro di aperture più ampio** — 75+ linee con le varianti principali, indicizzato
  **per posizione** (vale anche nelle trasposizioni), estendibile via `CHESS_BOOK_FILE`
  (file di testo `Nome: e2e4 e7e5 …`).
- [ ] **Import libro da PGN o formato Polyglot** (richiede parser SAN / hash Zobrist).
- [ ] **Potenziamenti di ricerca**: SEE (potare le catture perdenti in quiescence),
  aspiration windows alla radice, PVS, futility pruning ai nodi frontier.
- [ ] **Finali**: euristica "mop-up" (spingere il re avversario al bordo con materiale di
  vantaggio), riconoscimento KPK; eventuale mini-tablebase.
- [ ] **Pondering** — pensare durante il tempo dell'avversario (richiede la mossa async).
- [ ] **Livelli di difficoltà** selezionabili in partita (tempo/profondità/jitter più alto
  per i principianti), oltre al parametro globale `ai.engine_ms`.
- [ ] **Analisi post-partita** — valutazione del motore mossa per mossa, grafico
  dell'andamento, evidenziazione degli errori (?!, ??) nello storico.
- [ ] **Suggerimento mossa (hint)** per il giocatore umano, col motore a budget ridotto.
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
- [ ] **LLM come commentatore** — usare Qwen/Claude per commentare le partite in linguaggio
  naturale (dove i LLM rendono bene), non per scegliere le mosse.

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

- [ ] ⭐ **Sistema graduale di istruzione guidata** per imparare i giochi, con voce
  sintetica. Architettura proposta:
  - **Contenuti**: lezioni per gioco organizzate in **passi** (testo della spiegazione +
    posizione preimpostata sulla scacchiera + caselle/mosse da evidenziare + eventuale
    mossa richiesta all'allievo con verifica); progressione per gradi (es. scacchi: i
    pezzi uno alla volta → catture → arrocco/en passant → matti elementari → aperture).
  - **Progressi salvati** per utente (lezioni completate, da riprendere).
  - **UI**: modalità "lezione" sulla pagina di gioco esistente (riusa scacchiera,
    animazioni ed evidenziazioni), con pulsanti avanti/indietro e replay vocale.
  - **Voce**: ogni passo viene letto ad alta voce dal servizio TTS (sotto).
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
