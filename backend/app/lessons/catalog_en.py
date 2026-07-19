# ruff: noqa: E501 - dizionario: una voce per riga vale più del limite di colonna
"""Traduzione editoriale inglese dei CONTENUTI didattici (lezioni).

Stessa forma del catalogo principale (``app/catalog_en.py``, che lo fonde nel
dizionario unico usato da ``_()``): chiave = stringa italiana ESATTA come esce
dai moduli contenuto (``chess.py``, ``checkers.py``, ``tictactoe.py`` — occhio
alle concatenazioni implicite multiriga), valore = inglese. Vive accanto ai
contenuti che traduce: chi ritocca un testo qui a fianco aggiorna anche la
chiave, e il test di copertura (``test_lessons.py``) blocca ogni deriva —
titolo, passo o consegna senza traduzione fanno fallire la suite.
"""

LESSONS_EN = {
    # ----- Tris (tictactoe-base) -----
    "Imparare il Tris": "Learning Tic-Tac-Toe",
    "Il Tris si gioca in due su una griglia 3×3: a turno si mette il proprio segno, vince chi allinea TRE segni (riga, colonna o diagonale). Il centro è la casella più forte: tocca a te!": "Tic-Tac-Toe is a two-player game on a 3×3 grid: you take turns placing your mark, and whoever lines up THREE marks (row, column or diagonal) wins. The centre is the strongest square: your turn!",
    "Gioca la prima mossa nel centro.": "Play the first move in the centre.",
    "Mossa migliore!": "Best move!",
    "Quando hai DUE segni in fila e la terza casella è libera, chiudi subito: qui la tua fila in alto aspetta solo l'ultimo segno.": "When you have TWO marks in a row and the third square is free, close it right away: here your top row is only waiting for its last mark.",
    "Completa il tris in alto a destra.": "Complete the three-in-a-row at the top right.",
    "Tris! Vittoria!": "Three in a row! You win!",
    "Difendersi conta quanto attaccare: se l'AVVERSARIO ha due segni in fila, devi bloccare la terza casella prima che chiuda lui.": "Defending matters as much as attacking: if your OPPONENT has two marks in a row, you must block the third square before they close it.",
    "Blocca la fila dell'avversario!": "Block your opponent's row!",
    "Bloccato!": "Blocked!",
    # ----- Dama italiana (checkers-base) -----
    "Le basi della dama": "The basics of draughts",
    "Nella dama si gioca solo sulle case scure. La pedina muove in DIAGONALE, in avanti, di una casella alla volta.": "Draughts is played on the dark squares only. A piece moves DIAGONALLY, forward, one square at a time.",
    "Muovi la pedina in avanti, da e3 a d4.": "Move the piece forward, from e3 to d4.",
    "Così!": "Just like that!",
    "La presa è OBBLIGATORIA: se una pedina avversaria è davanti a te in diagonale e la casa dietro è libera, DEVI saltarla e catturarla.": "Capturing is MANDATORY: if an opponent's piece sits diagonally in front of you and the square behind it is free, you MUST jump over it and capture it.",
    "Salta la pedina nera: atterra in c5.": "Jump over the black piece: land on c5.",
    "Mangiata!": "Captured!",
    "Le prese possono essere MULTIPLE: se dopo un salto puoi saltarne subito un'altra, continui nella stessa mossa. Qui la bianca salta due pedine in un colpo solo.": "Captures can be MULTIPLE: if after one jump you can immediately take another piece, you carry on within the same move. Here White jumps two pieces in one go.",
    "Doppia presa: da e3 fino a e7.": "Double capture: from e3 all the way to e7.",
    "Doppietta!": "A double!",
    "Quando una pedina raggiunge l'ultima riga viene promossa a DAMA (⛁): da quel momento può muovere e catturare anche all'indietro.": "When a piece reaches the last row it is promoted to KING (⛁): from then on it can move and capture backwards too.",
    "Porta la pedina in b8 e diventa dama.": "Take the piece to b8 and make a king.",
    "Dama!": "King!",
    # ----- Scacchi: la scacchiera e l'obiettivo (chess-board) -----
    "La scacchiera e l'obiettivo": "The board and the goal",
    "Benvenuto! La scacchiera ha 64 case, alternate chiare e scure. Le quattro case centrali sono le più preziose: chi le controlla domina la partita.": "Welcome! The chessboard has 64 squares, alternating light and dark. The four central squares are the most precious: whoever controls them dominates the game.",
    "Questo è lo schieramento iniziale: ogni giocatore ha otto pedoni, due torri, due cavalli, due alfieri, una donna e un re. Il bianco muove sempre per primo.": "This is the starting position: each player has eight pawns, two rooks, two knights, two bishops, a queen and a king. White always moves first.",
    "L'obiettivo del gioco è dare scacco matto al re avversario: attaccarlo in modo che non abbia più alcuna casa sicura. Ecco i due re, i pezzi più importanti.": "The goal of the game is to checkmate the opponent's king: attack it so that it has no safe square left. Here are the two kings, the most important pieces.",
    # ----- Scacchi: il pedone (chess-pawn) -----
    "Il pedone": "The pawn",
    "Il pedone è il pezzo più numeroso: avanza di UNA casella in avanti, e non può mai tornare indietro.": "The pawn is the most numerous piece: it advances ONE square forward, and can never go back.",
    "Muovi il pedone di una casella, da e2 a e3.": "Move the pawn one square, from e2 to e3.",
    "Perfetto!": "Perfect!",
    "Dalla sua casa di partenza, il pedone può scegliere di avanzare di DUE caselle in un colpo solo.": "From its starting square, the pawn may choose to advance TWO squares in a single move.",
    "Prova il doppio passo: da e2 a e4.": "Try the double step: from e2 to e4.",
    "Ottimo doppio passo!": "A fine double step!",
    "Il pedone cattura in modo speciale: NON in avanti, ma in DIAGONALE. Qui il pedone bianco in e4 può catturare quello nero in d5.": "The pawn captures in a special way: NOT straight ahead, but DIAGONALLY. Here the white pawn on e4 can capture the black one on d5.",
    "Cattura il pedone nero in d5.": "Capture the black pawn on d5.",
    "Preso!": "Got it!",
    "Se un pedone arriva fino in fondo alla scacchiera viene PROMOSSO: si trasforma in un altro pezzo, quasi sempre una donna.": "If a pawn reaches the far end of the board it is PROMOTED: it turns into another piece, almost always a queen.",
    "Porta il pedone in e8 e promuovilo.": "Take the pawn to e8 and promote it.",
    "Una nuova donna!": "A brand-new queen!",
    # ----- Scacchi: la torre e l'alfiere (chess-rook-bishop) -----
    "La torre e l'alfiere": "The rook and the bishop",
    "La torre muove in linea RETTA: per righe e per colonne, di quante caselle vuole (finché non incontra un pezzo).": "The rook moves in a STRAIGHT line: along ranks and files, as many squares as it likes (until it meets a piece).",
    "Porta la torre in fondo alla colonna: d8.": "Take the rook to the end of the file: d8.",
    "Dritta!": "Straight ahead!",
    "L'alfiere muove solo in DIAGONALE, di quante caselle vuole. Ogni alfiere resta per sempre sulle case del proprio colore.": "The bishop moves only DIAGONALLY, as many squares as it likes. Each bishop stays forever on squares of its own colour.",
    "Fai scivolare l'alfiere fino a g7.": "Slide the bishop all the way to g7.",
    "In diagonale!": "Along the diagonal!",
    # ----- Scacchi: il cavallo (chess-knight) -----
    "Il cavallo": "The knight",
    "Il cavallo muove a «L»: due caselle in una direzione e una di lato. Da qui può raggiungere tutte le case evidenziate.": "The knight moves in an “L”: two squares in one direction and one to the side. From here it can reach all the highlighted squares.",
    "Il cavallo è l'unico pezzo che SALTA sopra gli altri: anche chiuso dietro i pedoni può uscire subito. È la mossa d'apertura più comune.": "The knight is the only piece that JUMPS over the others: even shut in behind the pawns it can come out at once. It is the most common opening move.",
    "Salta i pedoni: porta il cavallo in f3.": "Jump the pawns: take the knight to f3.",
    "Che balzo!": "What a leap!",
    # ----- Scacchi: la donna e il re (chess-queen-king) -----
    "La donna e il re": "The queen and the king",
    "La donna è il pezzo più potente: muove come torre E come alfiere, in tutte le direzioni per quante caselle vuole.": "The queen is the most powerful piece: it moves like a rook AND like a bishop, in every direction for as many squares as it likes.",
    "Porta la donna nell'angolo h8.": "Take the queen to the h8 corner.",
    "Regale!": "Regal!",
    "Il re muove in ogni direzione ma di UNA sola casella: è potente ma lento, e va sempre protetto.": "The king moves in every direction but only ONE square at a time: it is powerful yet slow, and must always be protected.",
    "Fai un passo avanti con il re: e5.": "Take one step forward with the king: e5.",
    "Con calma!": "Steady does it!",
    "Quando un pezzo attacca il re si dice SCACCO: qui la torre bianca inchioda la colonna «e» e il re nero è sotto tiro. Chi è sotto scacco DEVE rimediare subito: muovere il re, bloccare o catturare.": "When a piece attacks the king it is called CHECK: here the white rook commands the e-file and the black king is under fire. Whoever is in check MUST deal with it at once: move the king, block, or capture.",
    # ----- Scacchi: le mosse speciali (chess-special) -----
    "Le mosse speciali": "The special moves",
    "L'ARROCCO mette il re al sicuro e attiva la torre in una sola mossa: il re fa due passi verso la torre, che gli salta accanto. Vale solo se nessuno dei due ha già mosso e le case sono libere.": "CASTLING tucks the king away safely and activates the rook in a single move: the king takes two steps towards the rook, which hops to his side. It only works if neither has moved yet and the squares between them are free.",
    "Arrocca corto: re da e1 a g1.": "Castle short: king from e1 to g1.",
    "Re al sicuro!": "King safe!",
    "La presa AL VARCO (en passant): se un pedone avversario ti passa accanto col doppio passo, puoi catturarlo come se avesse mosso di una casella sola — ma solo alla mossa immediatamente successiva.": "The EN PASSANT capture: if an enemy pawn passes you by with its double step, you may capture it as if it had moved a single square — but only on the very next move.",
    "Cattura al varco: pedone in d6.": "Capture en passant: pawn to d6.",
    "Al varco!": "En passant!",
    # ----- Scacchi: il primo scacco matto (chess-mate) -----
    "Il primo scacco matto": "The first checkmate",
    "Ecco il matto più famoso: il MATTO DEL CORRIDOIO. Il re nero è chiuso dai suoi stessi pedoni; se la torre arriva in fondo alla colonna, lo scacco è… matto: nessuna casa di fuga!": "Here is the most famous mate of all: the BACK-RANK MATE. The black king is boxed in by his own pawns; if the rook reaches the end of the file, the check is… mate: no escape square!",
    "Dai scacco matto: torre in e8!": "Deliver checkmate: rook to e8!",
    "SCACCO MATTO! 🎉": "CHECKMATE! 🎉",
    "Complimenti, hai completato il corso base! Conosci i pezzi, le mosse speciali e il tuo primo matto. Ora mettiti alla prova: crea una partita contro Stockfish al livello Pan (Learner) oppure sfida un altro giocatore dalla Community.": "Congratulations, you have completed the basic course! You know the pieces, the special moves and your first mate. Now put yourself to the test: create a game against Stockfish at the Pan (Learner) level, or challenge another player from the Community.",
}
