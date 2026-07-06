"""Endpoint della voce sintetica (TTS) — vedi app/tts.py per il servizio.

- ``GET /tts?text=…&lang=it|en`` → WAV (dalla cache se già sintetizzato).
- ``GET /tts/status`` → motori e voci per lingua, disponibilità, cache.

Letture aperte: la sintesi serve al tutorial nel browser (tag ``<audio>``),
la protezione è nei limiti del servizio (lunghezza massima, cache, un solo
thread di sintesi) e nell'interruttore ``tts.enabled`` del super admin.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import tts
from ..database import get_db

router = APIRouter(prefix="/tts", tags=["tts"])


@router.get("/status")
def tts_status(db: Session = Depends(get_db)):
    """Stato per lingua (motore, voce, disponibilità) e statistiche della cache."""
    return tts.status(db)


@router.get("")
def speak(
    text: str = Query(default=""),
    lang: str | None = Query(default=None),
    speed: float | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Sintetizza il testo nella lingua richiesta e restituisce l'audio WAV."""
    try:
        path = tts.synthesize(db, text, lang=lang, speed=speed)
    except tts.TtsError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    return FileResponse(path, media_type="audio/wav", filename="speech.wav")
