"""Corso di scacchi: dai pezzi (uno alla volta) al primo scacco matto.

Progressione per gradi come da piano del tutorial: scacchiera → pedone →
pezzi maggiori → cavallo → donna e re → mosse speciali → matto elementare.
Le posizioni sono ILLUSTRATIVE (pochi pezzi, l'essenziale per il concetto).
"""

from __future__ import annotations

from engine import get_game

from . import path_task, pos8, sq, step

_INITIAL = get_game("chess").view_board(get_game("chess").initial_state())

LESSONS = [
    {
        "code": "chess-board",
        "game_code": "chess",
        "title": "La scacchiera e l'obiettivo",
        "order": 10,
        "steps": [
            step(
                "Benvenuto! La scacchiera ha 64 case, alternate chiare e scure. "
                "Le quattro case centrali sono le più preziose: chi le controlla "
                "domina la partita.",
                pos8({}),
                highlights=[sq("d4"), sq("e4"), sq("d5"), sq("e5")],
            ),
            step(
                "Questo è lo schieramento iniziale: ogni giocatore ha otto pedoni, "
                "due torri, due cavalli, due alfieri, una donna e un re. Il bianco "
                "muove sempre per primo.",
                list(_INITIAL),
            ),
            step(
                "L'obiettivo del gioco è dare scacco matto al re avversario: "
                "attaccarlo in modo che non abbia più alcuna casa sicura. "
                "Ecco i due re, i pezzi più importanti.",
                list(_INITIAL),
                highlights=[sq("e1"), sq("e8")],
            ),
        ],
    },
    {
        "code": "chess-pawn",
        "game_code": "chess",
        "title": "Il pedone",
        "order": 20,
        "steps": [
            step(
                "Il pedone è il pezzo più numeroso: avanza di UNA casella in avanti, "
                "e non può mai tornare indietro.",
                pos8({"e2": "♙"}),
                highlights=[sq("e3")],
                task=path_task(
                    "e2", "e3", "Muovi il pedone di una casella, da e2 a e3.", "Perfetto!"
                ),
            ),
            step(
                "Dalla sua casa di partenza, il pedone può scegliere di avanzare "
                "di DUE caselle in un colpo solo.",
                pos8({"e2": "♙"}),
                highlights=[sq("e4")],
                task=path_task(
                    "e2", "e4", "Prova il doppio passo: da e2 a e4.", "Ottimo doppio passo!"
                ),
            ),
            step(
                "Il pedone cattura in modo speciale: NON in avanti, ma in DIAGONALE. "
                "Qui il pedone bianco in e4 può catturare quello nero in d5.",
                pos8({"e4": "♙", "d5": "♟"}),
                highlights=[sq("d5")],
                task=path_task("e4", "d5", "Cattura il pedone nero in d5.", "Preso!"),
            ),
            step(
                "Se un pedone arriva fino in fondo alla scacchiera viene PROMOSSO: "
                "si trasforma in un altro pezzo, quasi sempre una donna.",
                pos8({"e7": "♙"}),
                highlights=[sq("e8")],
                task=path_task(
                    "e7", "e8", "Porta il pedone in e8 e promuovilo.", "Una nuova donna!"
                ),
            ),
        ],
    },
    {
        "code": "chess-rook-bishop",
        "game_code": "chess",
        "title": "La torre e l'alfiere",
        "order": 30,
        "steps": [
            step(
                "La torre muove in linea RETTA: per righe e per colonne, di quante "
                "caselle vuole (finché non incontra un pezzo).",
                pos8({"d4": "♖"}),
                highlights=[sq("d1"), sq("d8"), sq("a4"), sq("h4")],
                task=path_task("d4", "d8", "Porta la torre in fondo alla colonna: d8.", "Dritta!"),
            ),
            step(
                "L'alfiere muove solo in DIAGONALE, di quante caselle vuole. "
                "Ogni alfiere resta per sempre sulle case del proprio colore.",
                pos8({"d4": "♗"}),
                highlights=[sq("a1"), sq("h8"), sq("a7"), sq("g1")],
                task=path_task("d4", "g7", "Fai scivolare l'alfiere fino a g7.", "In diagonale!"),
            ),
        ],
    },
    {
        "code": "chess-knight",
        "game_code": "chess",
        "title": "Il cavallo",
        "order": 40,
        "steps": [
            step(
                "Il cavallo muove a «L»: due caselle in una direzione e una di lato. "
                "Da qui può raggiungere tutte le case evidenziate.",
                pos8({"d4": "♘"}),
                highlights=[
                    sq("b3"),
                    sq("b5"),
                    sq("c2"),
                    sq("c6"),
                    sq("e2"),
                    sq("e6"),
                    sq("f3"),
                    sq("f5"),
                ],
            ),
            step(
                "Il cavallo è l'unico pezzo che SALTA sopra gli altri: anche chiuso "
                "dietro i pedoni può uscire subito. È la mossa d'apertura più comune.",
                pos8({"g1": "♘", "e2": "♙", "f2": "♙", "g2": "♙", "h2": "♙"}),
                highlights=[sq("f3")],
                task=path_task("g1", "f3", "Salta i pedoni: porta il cavallo in f3.", "Che balzo!"),
            ),
        ],
    },
    {
        "code": "chess-queen-king",
        "game_code": "chess",
        "title": "La donna e il re",
        "order": 50,
        "steps": [
            step(
                "La donna è il pezzo più potente: muove come torre E come alfiere, "
                "in tutte le direzioni per quante caselle vuole.",
                pos8({"d4": "♕"}),
                highlights=[sq("d8"), sq("h4"), sq("h8"), sq("a1"), sq("a7")],
                task=path_task("d4", "h8", "Porta la donna nell'angolo h8.", "Regale!"),
            ),
            step(
                "Il re muove in ogni direzione ma di UNA sola casella: è potente "
                "ma lento, e va sempre protetto.",
                pos8({"e4": "♔"}),
                highlights=[
                    sq("d3"),
                    sq("e3"),
                    sq("f3"),
                    sq("d4"),
                    sq("f4"),
                    sq("d5"),
                    sq("e5"),
                    sq("f5"),
                ],
                task=path_task("e4", "e5", "Fai un passo avanti con il re: e5.", "Con calma!"),
            ),
            step(
                "Quando un pezzo attacca il re si dice SCACCO: qui la torre bianca "
                "inchioda la colonna «e» e il re nero è sotto tiro. Chi è sotto "
                "scacco DEVE rimediare subito: muovere il re, bloccare o catturare.",
                pos8({"e1": "♖", "e8": "♚"}),
                highlights=[sq("e1"), sq("e8")],
            ),
        ],
    },
    {
        "code": "chess-special",
        "game_code": "chess",
        "title": "Le mosse speciali",
        "order": 60,
        "steps": [
            step(
                "L'ARROCCO mette il re al sicuro e attiva la torre in una sola "
                "mossa: il re fa due passi verso la torre, che gli salta accanto. "
                "Vale solo se nessuno dei due ha già mosso e le case sono libere.",
                pos8({"e1": "♔", "h1": "♖", "a1": "♖"}),
                highlights=[sq("g1"), sq("f1")],
                task=path_task("e1", "g1", "Arrocca corto: re da e1 a g1.", "Re al sicuro!"),
            ),
            step(
                "La presa AL VARCO (en passant): se un pedone avversario ti passa "
                "accanto col doppio passo, puoi catturarlo come se avesse mosso di "
                "una casella sola — ma solo alla mossa immediatamente successiva.",
                pos8({"e5": "♙", "d5": "♟"}),
                highlights=[sq("d6")],
                task=path_task("e5", "d6", "Cattura al varco: pedone in d6.", "Al varco!"),
            ),
        ],
    },
    {
        "code": "chess-mate",
        "game_code": "chess",
        "title": "Il primo scacco matto",
        "order": 70,
        "steps": [
            step(
                "Ecco il matto più famoso: il MATTO DEL CORRIDOIO. Il re nero è "
                "chiuso dai suoi stessi pedoni; se la torre arriva in fondo alla "
                "colonna, lo scacco è… matto: nessuna casa di fuga!",
                pos8({"e1": "♖", "g8": "♚", "f7": "♟", "g7": "♟", "h7": "♟"}),
                highlights=[sq("e8")],
                task=path_task("e1", "e8", "Dai scacco matto: torre in e8!", "SCACCO MATTO! 🎉"),
            ),
            step(
                "Complimenti, hai completato il corso base! Conosci i pezzi, le "
                "mosse speciali e il tuo primo matto. Ora mettiti alla prova: "
                "crea una partita contro Stockfish al livello Pan (Learner) "
                "oppure sfida un altro giocatore dalla Community.",
                list(_INITIAL),
            ),
        ],
    },
]
