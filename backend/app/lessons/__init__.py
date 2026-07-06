"""Sistema graduale di istruzione guidata: registro delle lezioni.

Ogni LEZIONE appartiene a un gioco ed è una sequenza di PASSI. Un passo ha:

- ``text`` — la spiegazione (mostrata e letta ad alta voce dal servizio /tts);
- ``board`` — la posizione PREIMPOSTATA sulla scacchiera (lista lunga rows*cols
  con i simboli del motore: ♙♞…, ⛀⛂…, X/O — solo presentazione, nessun motore);
- ``highlights`` — indici delle caselle da evidenziare;
- ``task`` — facoltativo: la mossa richiesta all'allievo, verificata dal client:
  ``{"kind": "path", "from": i, "to": i, ...}`` per scacchi/dama (clic
  origine→destinazione) oppure ``{"kind": "cell", "cell": i, ...}`` per il Tris;
  con ``prompt`` (consegna) e ``success`` (feedback a mossa giusta).

I contenuti vivono nei moduli per gioco (``chess.py``, ``checkers.py``, …) e si
scrivono con gli helper qui sotto: ``pos8`` accetta coordinate scacchistiche
("e2") e vale anche per la dama (stessa griglia 8×8, bianco in basso).
Aggiungere una lezione = aggiungere un dict al modulo del gioco; l'integrità
del registro è verificata dai test (validate_lesson).
"""

from __future__ import annotations

from engine import get_game


def sq(coord: str) -> int:
    """Coordinate scacchistiche → indice della griglia 8×8 (riga 0 = ottava).

    Esempio: "e2" → 52. Vale per scacchi e dama (bianco in basso in entrambi).
    """
    file = ord(coord[0].lower()) - ord("a")
    rank = int(coord[1])
    if not (0 <= file < 8 and 1 <= rank <= 8):
        raise ValueError(f"Coordinata non valida: {coord}")
    return (8 - rank) * 8 + file


def pos8(pieces: dict[str, str]) -> list:
    """Posizione 8×8 da {coordinata: simbolo} (es. {"e2": "♙", "e8": "♚"})."""
    board: list = [None] * 64
    for coord, sym in pieces.items():
        board[sq(coord)] = sym
    return board


def pos_grid(rows: int, cols: int, cells: dict[int, str]) -> list:
    """Posizione generica da {indice: simbolo} (per Tris e giochi a griglia)."""
    board: list = [None] * (rows * cols)
    for idx, sym in cells.items():
        board[idx] = sym
    return board


def path_task(frm: str, to: str, prompt: str, success: str) -> dict:
    """Mossa richiesta origine→destinazione (scacchi/dama), in coordinate."""
    return {"kind": "path", "from": sq(frm), "to": sq(to), "prompt": prompt, "success": success}


def cell_task(cell: int, prompt: str, success: str) -> dict:
    """Mossa richiesta su una singola casella (giochi tipo Tris)."""
    return {"kind": "cell", "cell": cell, "prompt": prompt, "success": success}


def step(text: str, board: list, highlights: list[int] | None = None, task: dict | None = None):
    return {"text": text, "board": board, "highlights": highlights or [], "task": task}


def _collect() -> list[dict]:
    # Import locali per evitare cicli (i moduli contenuto usano gli helper sopra).
    from . import checkers, chess, tictactoe

    lessons = [*chess.LESSONS, *checkers.LESSONS, *tictactoe.LESSONS]
    return sorted(lessons, key=lambda le: (le["game_code"], le["order"]))


_CACHE: list[dict] | None = None


def all_lessons() -> list[dict]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _collect()
    return _CACHE


def get_lesson(code: str) -> dict | None:
    return next((le for le in all_lessons() if le["code"] == code), None)


def validate_lesson(lesson: dict) -> None:
    """Controlli di integrità (usati dai test): il contenuto sbagliato non parte."""
    game = get_game(lesson["game_code"])  # solleva se il gioco non esiste
    size = game.rows * game.cols
    assert lesson["code"] and lesson["title"], "code e title obbligatori"
    assert lesson["steps"], f"{lesson['code']}: nessun passo"
    for i, s in enumerate(lesson["steps"]):
        where = f"{lesson['code']} passo {i + 1}"
        assert s["text"].strip(), f"{where}: testo mancante"
        assert len(s["board"]) == size, f"{where}: board di {len(s['board'])} != {size}"
        assert all(0 <= h < size for h in s["highlights"]), f"{where}: highlight fuori griglia"
        task = s.get("task")
        if task:
            assert task["prompt"] and task["success"], f"{where}: task senza prompt/success"
            if task["kind"] == "path":
                assert 0 <= task["from"] < size and 0 <= task["to"] < size, (
                    f"{where}: task fuori griglia"
                )
                assert s["board"][task["from"]], f"{where}: nessun pezzo sull'origine del task"
            elif task["kind"] == "cell":
                assert 0 <= task["cell"] < size, f"{where}: cella del task fuori griglia"
            else:  # pragma: no cover - protezione per contenuti futuri
                raise AssertionError(f"{where}: kind di task sconosciuto {task['kind']}")
