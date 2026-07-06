"""Import del libro di aperture da file PGN: parser SAN + estrazione delle linee.

Il PGN scrive le mosse in notazione algebrica ABBREVIATA (SAN: ``Nf3``, ``exd5``,
``O-O``, ``e8=Q``, con disambiguazioni tipo ``Nbd7`` o ``R1e2``). Qui la SAN viene
tradotta in UCI **rigiocando la partita col motore**: per ogni token si cercano tra
le mosse legali quelle compatibili con pezzo, destinazione, disambiguazione e
promozione — se la compatibile è UNA sola, quella è la mossa. Niente tabelle
esterne: il motore è l'unica autorità sulla legalità.

Da ogni partita del PGN si estrae il prefisso di apertura (``max_plies``
semimosse) come linea del libro; il nome viene dai tag ``Opening``/``ECO`` se
presenti, altrimenti da Bianco–Nero. Il formato Polyglot (.bin, hash Zobrist)
non è supportato: voce separata nel TODO.
"""

from __future__ import annotations

import re

# Testo da ripulire nel movetext: commenti {…}, varianti (…) anche annidate,
# glifi $n, numeri di mossa "1." / "1..." e risultati finali.
_COMMENT_RE = re.compile(r"\{[^}]*\}")
_NAG_RE = re.compile(r"\$\d+")
_MOVE_NO_RE = re.compile(r"\b\d+\.(\.\.)?")
_RESULTS = {"1-0", "0-1", "1/2-1/2", "*"}
_TAG_RE = re.compile(r'^\[(\w+)\s+"([^"]*)"\]', re.M)


def _strip_variations(text: str) -> str:
    """Rimuove le varianti tra parentesi, gestendo l'annidamento."""
    out, depth = [], 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def san_to_uci(game, state, token: str) -> str | None:
    """Traduce un token SAN nella mossa UCI legale corrispondente (o ``None``).

    Confronto contro le mosse legali del motore: dal loro UCI si ricavano casa di
    partenza (e quindi il pezzo), destinazione e promozione — tutto ciò che serve
    a verificare la compatibilità con la SAN, disambiguazione inclusa.
    """
    token = token.rstrip("+#!?").replace("e.p.", "").strip()
    if not token:
        return None
    legal = {game.move_id(m): m for m in game.legal_moves(state)}

    if token in ("O-O", "O-O-O", "0-0", "0-0-0"):  # arrocco: mossa di re di due case
        short = token in ("O-O", "0-0")
        for uci in legal:
            piece = state.board[_sq(uci[:2])]
            if piece in ("K", "k") and uci[:2][0] == "e":
                if (short and uci[2] == "g") or (not short and uci[2] == "c"):
                    return uci
        return None

    promo = ""
    if "=" in token:
        token, _, promo = token.partition("=")
        promo = promo.lower()

    piece_letter = token[0] if token[0] in "KQRBN" else ""
    body = token[1:] if piece_letter else token
    body = body.replace("x", "")
    if len(body) < 2:
        return None
    target, hint = body[-2:], body[:-2]  # hint = disambiguazione (file e/o rank)

    matches = []
    for uci in legal:
        if uci[2:4] != target:
            continue
        if (uci[4:] or "") != promo:
            continue
        # Lo stato interno usa lettere ("P"/"n"/…, maiuscole = bianco): la lettera
        # SAN è la maiuscola del pezzo, vuota per il pedone.
        piece = (state.board[_sq(uci[:2])] or "").upper()
        if ("" if piece == "P" else piece) != piece_letter:
            continue
        if any(h not in uci[:2] for h in hint):  # "Nbd7": la partenza deve contenere 'b'
            continue
        matches.append(uci)
    return matches[0] if len(matches) == 1 else None


def _sq(coord: str) -> int:
    return (8 - int(coord[1])) * 8 + (ord(coord[0]) - ord("a"))


def parse_pgn(game, text: str, max_plies: int = 16) -> list[tuple[str, list[str]]]:
    """Estrae dal PGN una linea di libro per partita: (nome, prefisso di mosse UCI).

    Le partite con SAN non traducibile vengono troncate al prefisso valido (se
    resta almeno una mossa). ``max_plies`` limita la profondità: il libro serve
    per l'APERTURA, non per memorizzare partite intere.
    """
    lines: list[tuple[str, list[str]]] = []
    # Le partite sono separate dai blocchi di tag: si spezza sul primo tag "[Event".
    chunks = re.split(r"(?=^\[Event\b)", text, flags=re.M)
    for n, chunk in enumerate(c for c in chunks if c.strip()):
        tags = dict(_TAG_RE.findall(chunk))
        movetext = _TAG_RE.sub("", chunk)
        movetext = _strip_variations(_COMMENT_RE.sub(" ", movetext))
        movetext = _MOVE_NO_RE.sub(" ", _NAG_RE.sub(" ", movetext))
        tokens = [t for t in movetext.split() if t not in _RESULTS]

        state = game.initial_state()
        uci_line: list[str] = []
        for token in tokens[:max_plies]:
            uci = san_to_uci(game, state, token)
            if uci is None:
                break  # SAN non riconosciuta: si tiene il prefisso valido
            uci_line.append(uci)
            move = next(m for m in game.legal_moves(state) if game.move_id(m) == uci)
            state = game.apply(state, move)
        if not uci_line:
            continue
        name = tags.get("Opening") or (
            f"{tags['White']}–{tags['Black']}"
            if tags.get("White") and tags.get("Black")
            else f"PGN partita {n + 1}"
        )
        if tags.get("ECO") and tags.get("Opening"):
            name = f"{tags['ECO']} {name}"
        lines.append((name, uci_line))
    return lines
