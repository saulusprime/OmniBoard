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
L'IA è collegata a **Qwen**; se non è configurata una chiave API, gioca una strategia locale
ottimale (imbattibile a Tris). Quando muove l'IA, la sua mossa compare con un piccolo
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
