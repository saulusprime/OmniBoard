# TODO — Idee di potenziamento e miglioramento

> Backlog vivo del progetto: idee raccolte durante lo sviluppo, in ordine sparso dentro
> ogni categoria. Quando un punto viene realizzato, spuntarlo qui e documentarlo in
> [HANDOFF.md](./HANDOFF.md). Le voci con ⭐ sono quelle a maggior impatto percepito.

## Priorità alta

- [x] ⭐ **Mossa IA fuori dalla richiesta HTTP** — l'IA pensa in background e il client
  fa polling: niente attese bloccanti (2s/mossa) né richieste che durano minuti (IA-vs-IA).
- [ ] ⭐ **Autenticazione dei giocatori** — login/logout con sessione, password già hashate
  in anagrafica; senza, chiunque può giocare o registrare partite a nome di chiunque.
- [ ] **Migrazioni Alembic** — oggi `create_all`: ogni cambio schema richiede di ricreare il
  DB di sviluppo. Necessario anche per PostgreSQL in produzione.
- [ ] ⭐ **Gioco a distanza in tempo reale** — WebSocket (o polling strutturato) per partite
  umano-vs-umano su dispositivi diversi; presenza/turni; riconnessione.
- [ ] **Push GitHub** — configurare le credenziali (`gh auth login` o PAT) e pubblicare i
  commit locali in attesa su `origin/main`.

## Motore scacchi

- [ ] ⭐ **Avversario Stockfish (NNUE) configurabile** — integrare il vero motore Stockfish
  come avversario tramite protocollo **UCI** (binario esterno in subprocess; percorso da
  parametro super admin o `.env`, es. `STOCKFISH_PATH`). Forza regolabile: *Skill Level*
  0–20, `UCI_LimitStrength`/`UCI_Elo`, tempo o profondità per mossa — selezionabile al setup
  della partita (livelli di difficoltà "veri"). NNUE è la valutazione neurale integrata di
  Stockfish. Fallback automatico al motore interno se il binario non è disponibile; utile
  anche come **sparring/riferimento** per misurare la forza del motore interno e per
  l'analisi post-partita.
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

- [ ] ⭐ **Concorrenti IA multipli** (Claude, Gemini, Grok, Qwen, …) — oggi c'è un solo
  provider attivo globalmente; renderli **avversari selezionabili al setup della partita**
  («gioca contro Claude», «gioca contro Gemini»), ognuno con la propria configurazione/token
  nella pagina Provider IA. Da aggiungere ai provider: **Gemini** (Google) e **Grok** (xAI),
  entrambi con endpoint OpenAI-compatible. In prospettiva: profilo, punteggi e **classifica
  delle IA** (quale IA gioca meglio?), tornei IA-vs-IA tra provider diversi.
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
- [ ] **Nodi del caso**: Backgammon e Ludo (l'interfaccia `Game` ha già gli hook previsti).

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
