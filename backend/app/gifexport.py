"""Export della partita in GIF animata: un fotogramma per posizione.

Rendering con Pillow, nessuna dipendenza grafica esterna. I pezzi degli scacchi
sono glifi Unicode disegnati con un font di sistema che li contenga (lista di
percorsi noti + override con la variabile ``GIF_FONT``); se nessun font copre i
glifi si ripiega sulle LETTERE (K Q R B N P — sempre leggibili). Dama e Forza 4
sono disegnate come dischi (niente font), il Tris con X/O testuali.

Il backgammon non è supportato (griglia non quadrata, barra/uscite): 400.
"""

from __future__ import annotations

import io
import os

from PIL import Image, ImageDraw, ImageFont

# Colori delle case/pedine, coerenti col tema "legno" dell'interfaccia.
_LIGHT, _DARK = (240, 217, 181), (181, 136, 99)
_BG = (58, 36, 19)
_WHITE_PIECE, _BLACK_PIECE = (247, 241, 227), (43, 31, 20)

_CELL = 56  # lato di una casella in pixel
_FRAME_MS = 700  # durata di ogni fotogramma
_LAST_MS = 3000  # l'ultimo fotogramma resta a lungo (posizione finale)

# Glifo del motore → (glifo pieno, lettera di ripiego, è bianco?)
_CHESS = {
    "♔": ("♚", "K", True),
    "♕": ("♛", "Q", True),
    "♖": ("♜", "R", True),
    "♗": ("♝", "B", True),
    "♘": ("♞", "N", True),
    "♙": ("♟", "P", True),
    "♚": ("♚", "K", False),
    "♛": ("♛", "Q", False),
    "♜": ("♜", "R", False),
    "♝": ("♝", "B", False),
    "♞": ("♞", "N", False),
    "♟": ("♟", "P", False),
}
_DRAUGHTS_WHITE, _DRAUGHTS_KINGS = {"⛀", "⛁"}, {"⛁", "⛃"}

_FONT_CANDIDATES = [
    os.getenv("GIF_FONT") or "",
    "/System/Library/Fonts/Apple Symbols.ttf",  # macOS: copre i glifi degli scacchi
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]


def _load_font(size: int) -> tuple[ImageFont.FreeTypeFont | None, bool]:
    """(font, copre_i_glifi_scacchi). (None, False) = solo lettere/default."""
    for path in _FONT_CANDIDATES:
        if not path or not os.path.isfile(path):
            continue
        try:
            font = ImageFont.truetype(path, size)
        except OSError:
            continue
        try:
            box = font.getbbox("♚")
            return font, bool(box and box[2] > box[0])
        except (OSError, ValueError):
            return font, False
    return None, False


def supported(move_type: str) -> bool:
    return move_type in {"chess", "draughts", "cell", "column"}


def _draw_board(board: list, rows: int, cols: int, move_type: str, font_pack) -> Image.Image:
    font, has_glyphs, small = font_pack
    img = Image.new("RGB", (cols * _CELL + 16, rows * _CELL + 16), _BG)
    d = ImageDraw.Draw(img)
    for r in range(rows):
        for c in range(cols):
            x0, y0 = 8 + c * _CELL, 8 + r * _CELL
            dark = (r + c) % 2 == 1
            if move_type in ("chess", "draughts"):
                color = _DARK if dark else _LIGHT
            else:
                color = (43, 53, 67) if move_type == "cell" else (22, 29, 38)
            d.rectangle([x0, y0, x0 + _CELL - 1, y0 + _CELL - 1], fill=color)
            sym = board[r * cols + c]
            if not sym:
                continue
            cx, cy = x0 + _CELL // 2, y0 + _CELL // 2
            if move_type == "chess" and sym in _CHESS:
                glyph, letter, is_white = _CHESS[sym]
                fill = _WHITE_PIECE if is_white else _BLACK_PIECE
                text = glyph if has_glyphs else letter
                use = font if font else ImageFont.load_default()
                # Contorno di contrasto: il pezzo chiaro su casa chiara resta leggibile.
                d.text(
                    (cx, cy),
                    text,
                    font=use,
                    fill=fill,
                    anchor="mm",
                    stroke_width=2,
                    stroke_fill=_BLACK_PIECE if is_white else _LIGHT,
                )
            elif move_type == "draughts":
                is_white = sym in _DRAUGHTS_WHITE
                fill = _WHITE_PIECE if is_white else _BLACK_PIECE
                pad = 8
                d.ellipse(
                    [x0 + pad, y0 + pad, x0 + _CELL - pad, y0 + _CELL - pad],
                    fill=fill,
                    outline=_BLACK_PIECE if is_white else _LIGHT,
                    width=2,
                )
                if sym in _DRAUGHTS_KINGS:  # la dama ha la corona: un secondo anello
                    d.ellipse(
                        [x0 + pad + 8, y0 + pad + 8, x0 + _CELL - pad - 8, y0 + _CELL - pad - 8],
                        outline=_LIGHT if not is_white else _BLACK_PIECE,
                        width=2,
                    )
            elif sym in ("●", "○"):  # Othello e Gomoku: dischi pieni (niente font)
                is_white = sym == "○"
                pad = 8
                d.ellipse(
                    [x0 + pad, y0 + pad, x0 + _CELL - pad, y0 + _CELL - pad],
                    fill=_WHITE_PIECE if is_white else _BLACK_PIECE,
                    outline=_BLACK_PIECE if is_white else _LIGHT,
                    width=2,
                )
            else:  # Tris e Forza 4: X/O come testo pieno, ben contrastato
                fill = (232, 234, 237) if sym == "X" else (217, 164, 65)
                use = small if small else ImageFont.load_default()
                d.text((cx, cy), sym, font=use, fill=fill, anchor="mm")
    return img


def render_png(board: list, rows: int, cols: int, move_type: str) -> bytes:
    """PNG di una SINGOLA posizione (lo «screenshot» delle mosse geniali)."""
    font, has_glyphs = _load_font(int(_CELL * 0.78))
    small = font.font_variant(size=int(_CELL * 0.6)) if font else None
    img = _draw_board(board, rows, cols, move_type, (font, has_glyphs, small))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def render(boards: list[list], rows: int, cols: int, move_type: str) -> bytes:
    """GIF animata dalla sequenza di posizioni (una per semimossa, iniziale inclusa)."""
    font, has_glyphs = _load_font(int(_CELL * 0.78))
    small = font.font_variant(size=int(_CELL * 0.6)) if font else None
    pack = (font, has_glyphs, small)
    frames = [_draw_board(b, rows, cols, move_type, pack) for b in boards]
    out = io.BytesIO()
    durations = [_FRAME_MS] * len(frames)
    durations[-1] = _LAST_MS
    frames[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,  # riparte da capo all'infinito
    )
    return out.getvalue()
