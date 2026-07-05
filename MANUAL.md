# MANUAL — Manuale dei giochi e dell'applicazione

> Manuale d'uso della piattaforma **Scacchi** e regolamento di ogni gioco integrato.
> Ogni nuovo gioco aggiunto alla piattaforma va documentato qui seguendo il
> [modello per nuovi giochi](#modello-per-nuovi-giochi).
>
> **Ultimo aggiornamento:** 2026-06-28

---

## Indice

- [Parte 1 — Manuale dell'applicazione](#parte-1--manuale-dellapplicazione)
- [Parte 2 — Regolamento dei giochi](#parte-2--regolamento-dei-giochi)
  - [Scacchi](#scacchi)
  - [Dama italiana](#dama-italiana)
  - [Tris (Tic-Tac-Toe)](#tris-tic-tac-toe)
  - [Forza 4](#forza-4)
- [Modello per nuovi giochi](#modello-per-nuovi-giochi)

---

# Parte 1 — Manuale dell'applicazione

> ⚠️ L'applicazione è in sviluppo. Sono già disponibili: registrazione giocatori, gruppi
> (fondazione tramite voto), punteggi, classifiche e il **gioco del Tris** (umano vs umano,
> umano vs IA, IA vs IA). NON sono ancora disponibili: autenticazione/login, gli altri giochi
> e il gioco a distanza in tempo reale (il Tris fra due umani è per ora *hotseat*, sullo
> stesso schermo).

## Cos'è Scacchi

Scacchi è una piattaforma web per giocare in **due** a giochi da tavolo a turni
(scacchi, dama, tris, forza 4 e altri). Si gioca dal browser, senza installare nulla.

## Avvio e navigazione

Avvia backend e frontend (vedi [README.md](./README.md#avvio-rapido)) e apri
<http://127.0.0.1:8001/>. Il menu in alto dà accesso a: **Home**, **Giocatori**, **Gruppi**,
**Classifiche**, **Registra partita**.

## Funzionalità disponibili

### Creazione di un giocatore
Da **Giocatori → Nuovo giocatore** si registra un profilo con: nome, cognome, alias (univoco),
email (univoca), nazionalità e regione (queste ultime usate per le classifiche
nazionale/regionale). La password è opzionale in questa fase. Un utente può restare singolo o
far parte di uno o più gruppi.

### Gruppi e fondazione tramite voto
Da **Gruppi → Proponi un gruppo** si crea una proposta di fondazione; il proponente vota
automaticamente a favore. Quando i voti a favore raggiungono la soglia (almeno **2**), il
gruppo viene **fondato** e i votanti ne diventano membri (il proponente come *fondatore*). Le
regole di gestione del gruppo (ruoli, inviti, espulsioni) saranno definite più avanti.

### Punteggi e partite
Ogni giocatore ha un **punteggio per ciascun gioco**, che cresce giocando. Concludendo una
partita di **Tris** i punteggi dei giocatori umani si aggiornano in automatico; in più si
possono inserire risultati manualmente da **Registra partita** (vittoria +3, patta +1,
sconfitta +0). Il dettaglio dei punteggi è nella scheda del giocatore.

### Classifiche e gamification
- **Classifica universale**: somma dei punti di un giocatore su *tutti* i giochi → è la base
  della gamification.
- **Classifica per gioco**, con ambito **globale**, **nazionale** (per nazionalità) o
  **regionale** (per regione).

### Super admin (parametri di programma)
Dal menu **Admin** si accede all'interfaccia di amministrazione, dove **tutti i parametri**
del programma sono modificabili: nome del sito, abilitazione delle registrazioni, punti per
vittoria/patta/sconfitta, voti minimi per fondare un gruppo, ritardo della mossa dell'IA,
numero massimo di partite consecutive, ecc. I parametri sono raggruppati per categoria; per
salvare una modifica occorre inserire il **token super admin** (configurato sul server con la
variabile `ADMIN_TOKEN`). Le modifiche hanno effetto immediato.

### Aspetto: animazione delle mosse ed effetto sonoro
Nella pagina di gioco i pezzi **scivolano** dalla casella di origine a quella di
destinazione (negli scacchi anche arrocco e presa al varco sono animati; nel Forza 4 la
pedina *cade* nella colonna; nel Tris il simbolo compare con un breve "pop"). Ogni mossa è
accompagnata da un **effetto sonoro** discreto, più grave quando c'è una cattura — il suono
è sintetizzato dal browser (WebAudio): non viene scaricato alcun file. Nota: i browser
attivano l'audio solo dopo il primo click sulla pagina.

Dal super admin (categoria **Aspetto**) si personalizzano: la **durata dell'animazione**
(`ui.anim_ms`, millisecondi; 0 = pezzi che si spostano all'istante), l'**abilitazione del
suono** (`ui.sound_enabled`) e il **volume** (`ui.sound_volume`, 0-100). Le modifiche hanno
effetto al ricaricamento della pagina di gioco.

### Provider IA (login verso Qwen, Claude, OpenAI…)
Dalla pagina **Provider IA** (pulsante in cima alla pagina Admin, oppure `/admin/ia/`) si
configurano i servizi di intelligenza artificiale **senza toccare il file `.env`**. Per ogni
provider (Qwen, Claude/Anthropic, OpenAI) si imposta l'endpoint, il modello e il **token/API key**,
e si sceglie quale provider è **attivo** (oppure «Nessuno» per usare solo il giocatore locale).
Il pulsante **«Verifica connessione»** prova le credenziali con una chiamata minima. Anche qui il
salvataggio richiede il **token super admin**. Per sicurezza il token del provider **non viene
mai rimostrato**: se è già impostato compare l'etichetta «configurato» e lasciando il campo vuoto
si conserva quello esistente. Se nessun provider attivo ha un token valido, l'IA gioca in
**locale** (minimax con potatura alpha-beta).

## Concetti generali di gioco

- **Due giocatori.** Ogni partita è tra due giocatori.
- **Turni.** Si alternano le mosse; in alcuni giochi esiste un giocatore che muove per primo.
- **Mosse legali.** L'interfaccia proporrà solo mosse valide; il server sarà l'arbitro finale
  (quando il motore di gioco sarà collegato).
- **Esito.** Vittoria, sconfitta o patta, secondo le regole del gioco.

---

# Parte 2 — Regolamento dei giochi

## Scacchi

**Giocatori:** 2 (Bianco e Nero). **Tavoliere:** 8×8 (64 caselle).
**Obiettivo:** dare **scacco matto** al re avversario.

### Disposizione iniziale
Ogni giocatore dispone di: 1 re, 1 donna, 2 torri, 2 alfieri, 2 cavalli, 8 pedoni.
Il Bianco muove per primo. La casella in basso a destra è chiara («bianco a destra»); la donna
va sulla casella del proprio colore («donna sul suo colore»).

### Movimento dei pezzi
- **Re:** una casella in qualsiasi direzione.
- **Donna:** in linea retta (orizzontale, verticale, diagonale) per qualsiasi distanza.
- **Torre:** in orizzontale e verticale per qualsiasi distanza.
- **Alfiere:** in diagonale per qualsiasi distanza.
- **Cavallo:** a «L» (2+1 caselle); è l'unico pezzo che scavalca gli altri.
- **Pedone:** avanza di una casella (due dalla posizione iniziale); cattura in diagonale.

### Mosse speciali
- **Arrocco:** mossa congiunta di re e torre, se nessuno dei due si è mosso, non ci sono pezzi
  fra loro, il re non è sotto scacco e non attraversa caselle attaccate.
- **En passant:** cattura speciale di un pedone avversario che è appena avanzato di due caselle.
- **Promozione:** un pedone che raggiunge l'ultima traversa viene promosso (di norma a donna).

### Fine della partita
- **Scacco matto:** il re è sotto attacco e non esistono mosse legali → vittoria.
- **Stallo (patta):** il giocatore di turno non ha mosse legali ma non è sotto scacco.
- **Altre patte:** materiale insufficiente, triplice ripetizione, regola delle 50 mosse,
  accordo tra i giocatori.

### Come giocarci nell'app
Dal menu **Gioca** scegli **Scacchi** e imposta i due lati (umano o IA). Clicca un tuo pezzo:
l'app evidenzia le case raggiungibili; clicca la destinazione per muovere. Arrocco (muovi il re
di due case), en passant e promozione sono gestiti automaticamente; in caso di promozione l'app
chiede quale pezzo (Donna/Torre/Alfiere/Cavallo). Durante la partita viene mostrato il **nome
dell'apertura** riconosciuta (es. *Partita Italiana*, *Difesa Siciliana*, *Partita Scozzese*).

### Tecniche di apertura
L'app riconosce le aperture dal **libro integrato** — oltre 70 linee con le varianti
principali: Italiana (Giuoco Piano, Evans), Spagnola (chiusa, aperta, Berlinese, di cambio),
Scozzese, Petroff, gambetti di Re e Danese, Siciliana (Najdorf, Dragone, Sveshnikov,
Taimanov, Kan, Alapin, Rossolimo…), Francese (avanzata, Tarrasch, Winawer), Caro-Kann
(classica, Panov), Scandinava, Alekhine, Pirc, Gambetto di Donna (rifiutato, accettato,
Tarrasch), Slava e Semi-Slava, Catalana, Londra, Colle, Est-Indiana, Nimzo, Grünfeld,
Ovest-Indiana, Benoni, Benko, Olandese, Inglese, Réti e altre. Il nome mostrato diventa più
specifico man mano che la variante si delinea (es. *Difesa Siciliana* → *Siciliana Najdorf*).

L'**IA segue le linee di libro** nelle prime mosse — il libro è indicizzato **per posizione**,
quindi funziona anche nelle **trasposizioni** (stessa posizione raggiunta con un ordine di
mosse diverso) — e poi prosegue con la propria ricerca. Il libro si può **estendere senza
toccare il codice**: imposta `CHESS_BOOK_FILE` nel `.env` con il percorso di un file di testo
(una linea per riga, `Nome apertura: e2e4 e7e5 …`). *Nota:* non è ancora gestita la patta per
**triplice ripetizione**.

### L'orologio di gioco (cadenze di torneo)
Per gli scacchi, al setup della partita puoi attivare l'**orologio**: ogni giocatore ha un
tempo totale che scorre solo durante il proprio turno; chi lo esaurisce **perde per tempo**
(«caduta della bandierina») — è patta se all'avversario resta il re nudo. Le categorie:

| Categoria | Tempo a testa | Note |
|---|---|---|
| **Blitz / Lampo** | meno di 15′ (es. 3′+2″) | minuti configurabili 1–14 |
| **Rapid / Rapido** | 15–60′ | minuti configurabili |
| **Classical / Classico** | oltre 60′ | minuti configurabili 61–600 |
| **FIDE ufficiale** | 90′ + 30″ a mossa | +30′ dopo la 40ª mossa; parametri fissi |

Per Blitz, Rapid e Classical puoi attivare l'**incremento Fischer** (o *bonus*): a ogni
mossa completata l'orologio riaccredita un numero fisso di secondi (es. 3″ o 5″,
configurabile 0–60). La notazione `3′+2″` significa «3 minuti a testa più 2 secondi a
mossa». Il formato FIDE ha già il suo incremento di 30″ e non è personalizzabile.

In partita i due orologi compaiono sopra la scacchiera: quello del giocatore al tratto è
evidenziato e sotto i 30 secondi diventa rosso. L'arbitro è il **server**: il tempo viene
scalato a ogni mossa e la bandierina viene constatata anche se nessuno muove più. Contro
l'IA anche il suo orologio scorre mentre pensa (il tempo di riflessione viene limitato
automaticamente perché non perda per tempo).

### L'IA degli scacchi (motore)
Finita l'apertura, l'IA usa un **motore di ricerca dedicato** (alpha-beta con *iterative
deepening*, *transposition table* e *quiescence search*) che **analizza la scacchiera in
profondità mossa dopo mossa**: valuta materiale, posizione dei pezzi, struttura dei pedoni,
sicurezza del re e altro, trova matti e combinazioni forzate ed evita di lasciare pezzi in presa.
Il tempo di analisi per mossa è regolabile dal super admin (parametro *Tempo di analisi del
motore scacchi*, default 2 secondi): più tempo = gioco più forte. Per gli scacchi il motore locale
è preferito a un eventuale provider IA remoto perché più forte.

### I tre tipi di avversario
Al setup della partita ogni lato (X e O) può essere di **tre tipi**:

- **Umano** — un giocatore registrato (si gioca a turni sullo stesso schermo).
- **IA via API** — la mossa viene chiesta al **provider IA attivo** (Qwen, Claude, … —
  configurato in *Provider IA*). Se nessun provider è attivo o la chiamata fallisce,
  gioca il **giocatore locale** (per gli scacchi il motore interno).
- **Stockfish (motore)** — il celebre motore open source con valutazione neurale (NNUE),
  se installato sul server (`brew install stockfish` / `apt install stockfish`). Si sceglie
  uno dei **sei livelli preconfigurati**, dal più forte al più debole:

  | Livello | Difficoltà | Elo simulato | Tempo/mossa |
  |---|---|---|---|
  | **Zeus** | Extreme | piena forza | 4 s |
  | **Atena** | Master | 2700 | 2,5 s |
  | **Apollo** | Champion | 2350 | 1,8 s |
  | **Ares** | Expert | 2000 | 1,2 s |
  | **Hermes** | Middle | 1700 | 0,8 s |
  | **Pan** | Learner | 1400 | 0,5 s |

  L'Elo simulato usa `UCI_LimitStrength` di Stockfish: il modo più realistico di giocare
  contro un "umano" di quella forza. Il percorso del binario resta quello globale del
  super admin (categoria *Stockfish*), dove esistono anche i parametri manuali usati
  quando una sessione non specifica il livello. Se il binario non c'è, ripiega sul
  motore interno.

In partita, sotto il nome dei giocatori è indicato il tipo di ciascun lato; la partita non
si blocca mai: qualunque problema dell'avversario scelto fa subentrare il giocatore locale.

#### Come verificare che Stockfish sia installato e usato davvero
1. **Installazione**: `brew install stockfish` (o binario ufficiale da stockfishchess.org
   reso eseguibile). Prova rapida da terminale: `echo uci | stockfish` deve stampare
   `uciok`.
2. **Verifica dall'app**: pagina **Admin** → pulsante **«Verifica Stockfish»** (col token
   super admin): riporta nome e versione del motore, la mossa di prova e il **percorso
   risolto** (parametro `stockfish.path` → variabile `STOCKFISH_PATH` → ricerca nel PATH).
3. **In partita**: sotto la scacchiera compare **«Ultima mossa IA: …»** — se dice
   *Stockfish* ha giocato il motore; *libro aperture* è normale nelle prime mosse; se dice
   *motore interno* o *minimax locale* è scattato il ripiego (binario non trovato o in
   errore: ricontrolla il punto 2).

### Modello dell'avversario
Quando l'IA affronta un giocatore umano, analizza lo **storico delle sue partite di scacchi** per
individuarne **schemi e debolezze**: aperture giocate e relativo rendimento, fragilità tattica
(sconfitte rapide), tendenza alla patta, tenuta nei finali. In base al profilo **adatta il proprio
stile**: più **aggressiva** contro chi crolla presto, più **anti-patta** (evita le semplificazioni)
contro chi pareggia spesso. Il profilo è consultabile nella scheda del giocatore (pannello
«Profilo scacchistico») ed è ciò che l'IA usa per prepararsi all'avversario.

---

## Dama italiana

**Giocatori:** 2. **Tavoliere:** 8×8, si gioca sulle caselle scure. **Pedine:** 12 per parte.
**Obiettivo:** catturare o bloccare tutte le pedine avversarie.

### Regole principali (variante italiana / FID)
- Le pedine muovono in diagonale in avanti di una casella.
- La **cattura** avviene saltando una pedina avversaria adiacente con casella libera oltre.
- La cattura è **obbligatoria**; in caso di scelte multiple valgono le regole di precedenza
  della variante italiana (es. si deve eseguire la presa che cattura più pezzi).
- Una pedina **non** può catturare una dama (regola tipica della variante italiana).
- Raggiungendo l'ultima traversa la pedina diventa **dama** e può muovere/catturare anche
  all'indietro.

### Fine della partita
Vince chi cattura tutte le pedine avversarie o lascia l'avversario senza mosse legali.

### Come giocarci nell'app
Dal menu **Gioca** scegli **Dama italiana** e imposta i due lati (umano o IA). Clicca una tua
pedina (Bianco = ⛀/⛁, Nero = ⛂/⛃): l'app evidenzia le destinazioni possibili; clicca la
casella di arrivo per muovere. Quando è disponibile una **cattura** la mossa è obbligatoria e
l'app propone solo le catture (col massimo numero di prese). Contro l'IA la risposta avversaria
compare con un breve ritardo.

> Note sull'implementazione attuale: non sono ancora applicate le priorità FID fini tra catture
> di pari numero (preferire la dama, catturare più dame, prima le dame) né le patte per
> ripetizione; saranno affinate in seguito.

> Nota: esistono diverse varianti di dama (italiana, inglese/checkers, internazionale).
> Questa sezione descrive la **dama italiana**; eventuali altre varianti integrate saranno
> documentate separatamente.

---

## Tris (Tic-Tac-Toe)

**Giocatori:** 2 (X e O). **Tavoliere:** 3×3.
**Obiettivo:** allineare tre dei propri simboli in orizzontale, verticale o diagonale.

### Regole
- I giocatori, a turno, posizionano il proprio simbolo in una casella libera.
- Vince chi completa per primo una fila di tre.
- Se la griglia si riempie senza allineamenti, la partita è **patta**.

### Come giocarci nell'app
Dal menu **Gioca** scegli chi controlla **X** (muove per primo) e **O**: ogni lato può essere
un giocatore **umano** oppure l'**IA**. Per giocare in due, imposta entrambi i lati su «Umano»
(si gioca a turni sullo stesso schermo). Clicca una casella libera per muovere; se l'avversario
è l'IA, risponde subito. A fine partita i punteggi dei giocatori umani vengono aggiornati.
L'IA può usare un **provider remoto** (Qwen, Claude o OpenAI, configurato in *Provider IA*); se
nessuno è attivo o configurato, gioca una strategia locale ottimale (imbattibile a Tris). Quando
muove l'IA, la sua mossa compare con un piccolo
**ritardo** e un'**animazione** (durante l'attesa vedi «L'IA sta pensando»). Se imposti
**entrambi i lati come IA**, puoi indicare un numero di **partite consecutive** (es. 100):
l'app le gioca tutte e mostra il riepilogo (vittorie X, vittorie O, patte).

Durante la partita, accanto alla scacchiera, un **widget** mostra il **log delle mosse**
(es. «X → b2»). A fine partita il log viene salvato nello **storico di entrambi i giocatori**:
lo trovi nella scheda di ciascun giocatore, sezione «Storico partite», con l'esito e il
dettaglio delle mosse.

---

## Forza 4

**Giocatori:** 2. **Tavoliere:** griglia verticale 7 colonne × 6 righe.
**Obiettivo:** allineare quattro proprie pedine consecutive.

### Regole
- A turno si fa cadere una pedina in una colonna; occupa la posizione libera più in basso.
- Vince chi allinea **quattro** pedine consecutive in orizzontale, verticale o diagonale.
- Se la griglia si riempie senza allineamenti, la partita è **patta**.

### Come giocarci nell'app
Dal menu **Gioca** scegli **Forza 4** e imposta i due lati (umano o IA). Per muovere, usa i
pulsanti **▼** sopra le colonne (oppure giochi in due sullo stesso schermo). La pedina cade
nella posizione libera più in basso. Contro l'IA la mossa avversaria compare con un breve
ritardo e animazione. L'IA di Forza 4 usa il provider remoto attivo (Qwen/Claude/OpenAI) se
configurato, altrimenti una strategia locale con ricerca a profondità limitata (forte ma non
imbattibile).

---

## Modello per nuovi giochi

Per documentare un nuovo gioco, copiare questo schema:

```markdown
## <Nome del gioco>

**Giocatori:** 2. **Tavoliere:** <dimensioni/forma>.
**Obiettivo:** <condizione di vittoria>.

### Disposizione iniziale
<come si parte>

### Regole di movimento / azioni
<mosse ammesse>

### Mosse speciali / casi particolari
<se presenti — incl. eventuali nodi del caso/dadi>

### Fine della partita
<vittoria / sconfitta / patta>
```
