# TODO — Idee di potenziamento e miglioramento

> Backlog vivo del progetto: idee raccolte durante lo sviluppo, in ordine sparso dentro
> ogni categoria. Quando un punto viene realizzato, spostarlo in [ASIS.md](./ASIS.md)
> e documentarlo in [HANDOFF.md](./HANDOFF.md). Le voci con ⭐ sono quelle a maggior
> impatto percepito.

## Frontend — rifiniture dell'IA ad aree

> La riorganizzazione sul modello chess.com è **COMPLETA** (5 fasi, 2026-07-11,
> v. ASIS.md): navbar a 5 aree con menu a discesa, hub Gioca e Guarda,
> Community ristretta con /notifiche/, home-cruscotto per il loggato.

- [ ] Rifiniture: **ricerca giocatore in navbar**, titoli di pagina e
  breadcrumb coerenti con le aree.

## Giochi

- [ ] **Filetto 3D** (4×4×4): richiede un tavoliere 3D dedicato nel frontend
  (piani impilati o proiezione); Othello e Gomoku sono FATTI (v. ASIS.md).
- [ ] Backgammon: affinamenti — tiro iniziale "un dado a testa", regola del dado
  maggiore obbligatorio, cubo del raddoppio, punteggi gammon/backgammon, IA
  expectiminimax (oggi greedy dado per dado).
- [ ] **Ludo** (nodi del caso, come il backgammon).

## Frontend / UX

- [ ] **i18n (contenuti)** — traduzione EDITORIALE dei contenuti delle lezioni
  (`lessons/`, testo didattico lungo): la pipeline c'è (stesso `_()`),
  mancano le traduzioni.

## Sicurezza / DevOps

- [ ] **WebSocket** al posto del polling — il candidato infrastrutturale più
  maturo (2026-07-11): oggi il polling regge mosse a distanza, presenza,
  campanella delle notifiche, dirette degli spettatori e tabelloni dei tornei;
  un canale unico li sostituirebbe tutti.
- [ ] **Rate limiting** sulle API pubbliche; configurazione **CORS** esplicita.
- [ ] **Audit log** delle operazioni super admin.
- [ ] **Docker Compose** (backend + frontend + PostgreSQL) per sviluppo e deploy.

## Statistiche avanzate del giocatore (idee da chess.com «Insights», 2026-07-07)

> Fonte studiata: chess.com/it/news/view/annuncio-statistiche-avanzate (funzione
> premium «Diamond»; da noi sarebbe GRATIS). Materia prima già in casa: analisi in
> cache (`analysis_json`), badge di qualità per mossa (`moves_json.quality`),
> `profile["accuracy"]`, `tc_category` sulle sessioni. Più partite analizzate =
> insights più ricchi (sinergia col pulsante «Analizza lo storico»). Le voci
> realizzate (pagina Statistiche, mosse geniali, cadenze, quattro aspetti,
> sottocategorie tattiche, pari fascia) sono in [ASIS.md](./ASIS.md).

- [ ] **Punteggio aggregato per categoria con peso alla recency**: le partite recenti
  contano più delle vecchie (decadimento esponenziale), come i rating.

## Visione — coaching, community e creator (idee del 2026-07-06, con valutazione)

> Sei proposte analizzate e ordinate per rapporto valore/sforzo. Prima le **primitive
> trasversali** che le sbloccano quasi tutte: costruite quelle, il resto è assemblaggio.
> Le primitive già realizzate (sistema puzzle, rating Elo) e l'AI Coach completo
> (spiegami la mossa, tilt, bias cognitivi) sono in [ASIS.md](./ASIS.md).

### Primitive mancanti (prerequisiti condivisi)

- [ ] **Valuta virtuale** (guadagnata con puzzle/partite/lezioni; mai convertibile in
  denaro) — serve a: pronostici watch party, ricompense creator, mentorship.
- [ ] **Presenza spettatori per partita** (chi sta guardando la sessione N; riusa
  l'infrastruttura heartbeat della community) — serve a: watch party, heatmap, OBS.

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

**Ordine consigliato:** Editor Puzzle Story → Valuta virtuale → Watch party → Clan wars
→ OBS (Puzzle e AI Coach, i primi due della fila originale, sono fatti: v. ASIS.md).
