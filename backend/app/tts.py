"""Servizio di sintesi vocale (TTS) multi-motore con gestione delle lingue.

Un'unica astrazione davanti a DUE motori locali (ONNX, solo CPU, nessun cloud):

- **Piper** — voci multilingua (qui usato per l'ITALIANO, es. ``it_IT-paola-medium``).
  Dipendenza *opzionale* (``pip install piper-tts``, licenza GPL-3: per questo non
  sta in requirements.txt — l'installazione è una scelta dell'operatore). La voce
  (.onnx + .json) viene scaricata da HuggingFace al primo uso nella cartella
  ``backend/tts_voices/``.
- **KittenTTS** — voci INGLESI (submodule ``integrazioni/KittenTTS``, Apache 2.0,
  già dipendenza del backend); il modello si scarica da HuggingFace al primo uso.

La LINGUA decide il motore: ogni lingua ha un parametro di programma
(``tts.voice_it``, ``tts.voice_en``) col formato ``"motore:voce"`` — così il super
admin può cambiare voce o motore senza toccare il codice (es. inglese con Piper:
``piper:en_US-lessac-medium``).

Design per un tutorial a testi FISSI:

- **cache su disco** (``backend/tts_cache/``): ogni frase si sintetizza una volta
  sola; le richieste successive servono il WAV dal disco (anche se nel frattempo
  il motore non è più disponibile);
- **import pigri**: nessun modello caricato all'avvio; se un motore manca il
  servizio risponde 503 con un messaggio che spiega cosa installare (il tutorial
  resta testuale);
- i modelli restano in memoria dopo il primo uso (le lezioni fanno molte frasi).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
import wave
from pathlib import Path

from sqlalchemy.orm import Session

from . import settings_service

_BACKEND_DIR = Path(__file__).resolve().parents[1]

# Lingua → chiave del parametro con la voce ("motore:voce"). Aggiungere una lingua
# = aggiungere una voce qui e il parametro corrispondente in settings_service.
LANG_SETTINGS = {
    "it": "tts.voice_it",
    "en": "tts.voice_en",
}

# Un solo thread sintetizza alla volta: i modelli ONNX non sono garantiti
# thread-safe e la CPU è comunque il collo di bottiglia.
_synth_lock = threading.Lock()
# Singleton pigri dei modelli caricati (voce → istanza).
_kitten_model = None
_piper_voices: dict[str, object] = {}


class TtsError(Exception):
    """Errore del servizio TTS, con lo status HTTP suggerito."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def cache_dir() -> Path:
    """Cartella della cache WAV (override con TTS_CACHE_DIR nei test)."""
    return Path(os.getenv("TTS_CACHE_DIR") or _BACKEND_DIR / "tts_cache")


def voices_dir() -> Path:
    """Cartella delle voci Piper (override con TTS_VOICES_DIR)."""
    return Path(os.getenv("TTS_VOICES_DIR") or _BACKEND_DIR / "tts_voices")


def parse_voice_spec(spec: str) -> tuple[str, str]:
    """Scinde ``"motore:voce"`` (es. ``"piper:it_IT-paola-medium"``) in (motore, voce)."""
    engine, _, voice = (spec or "").partition(":")
    engine, voice = engine.strip(), voice.strip()
    if engine not in ENGINES or not voice:
        raise TtsError(500, f"Voce TTS mal configurata: «{spec}» (atteso motore:voce)")
    return engine, voice


# ----- Motori ---------------------------------------------------------------------
# Ogni motore è una funzione (text, voice, speed, out_path) che scrive un WAV.
# Il registro è monkeypatch-abile nei test (motori finti, nessun modello reale).


def _synth_kitten(text: str, voice: str, speed: float, out_path: Path) -> None:
    """KittenTTS (inglese): modello HuggingFace scaricato al primo uso, poi in RAM."""
    try:
        import soundfile
        from kittentts import KittenTTS
    except ImportError as exc:  # pragma: no cover - dipende dall'ambiente
        raise TtsError(503, f"KittenTTS non installato: {exc}") from exc
    global _kitten_model
    if _kitten_model is None:
        _kitten_model = KittenTTS()  # nano di default: ~15M, 1-2s di sintesi su CPU
    audio = _kitten_model.generate(text, voice=voice, speed=speed)
    soundfile.write(str(out_path), audio, 24000)


def _piper_voice_files(voice: str) -> Path:
    return voices_dir() / f"{voice}.onnx"


def _download_piper_voice(voice: str) -> None:
    """Scarica la voce da HuggingFace (una tantum) nella cartella delle voci.

    Si usa il modulo ufficiale via subprocess: l'interfaccia a riga di comando è
    più stabile dell'API interna e non tiene dipendenze extra nel processo.
    """
    voices_dir().mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    try:
        # Il Python di python.org su macOS non vede i certificati di sistema e il
        # download (urllib) fallirebbe con CERTIFICATE_VERIFY_FAILED: si passa il
        # bundle di certifi (già presente nel venv come dipendenza di httpx).
        import certifi

        env.setdefault("SSL_CERT_FILE", certifi.where())
    except ImportError:  # pragma: no cover - certifi arriva con httpx
        pass
    result = subprocess.run(
        [sys.executable, "-m", "piper.download_voices", voice, "--data-dir", str(voices_dir())],
        capture_output=True,
        text=True,
        timeout=600,  # una voce "medium" pesa ~60 MB
        env=env,
    )
    if result.returncode != 0 or not _piper_voice_files(voice).exists():
        raise TtsError(
            503,
            f"Voce Piper «{voice}» non disponibile e download fallito: "
            f"{(result.stderr or result.stdout).strip()[:300]}",
        )


def _synth_piper(text: str, voice: str, speed: float, out_path: Path) -> None:
    """Piper (italiano e multilingua): voce .onnx locale, scaricata al primo uso."""
    try:
        from piper import PiperVoice, SynthesisConfig
    except ImportError as exc:
        raise TtsError(
            503,
            "Piper non installato: l'operatore può abilitarlo con "
            f"`pip install piper-tts` (licenza GPL-3, scelta esplicita). Dettaglio: {exc}",
        ) from exc
    if voice not in _piper_voices:
        model_path = _piper_voice_files(voice)
        if not model_path.exists():
            _download_piper_voice(voice)
        _piper_voices[voice] = PiperVoice.load(model_path)
    # length_scale è l'inverso della velocità: 1.25x più veloce → scala 0.8.
    cfg = SynthesisConfig(length_scale=1.0 / max(0.25, min(4.0, speed)))
    with wave.open(str(out_path), "wb") as wav_file:
        _piper_voices[voice].synthesize_wav(text, wav_file, syn_config=cfg)


ENGINES = {"kitten": _synth_kitten, "piper": _synth_piper}


# ----- Disponibilità (per /tts/status: nessun download, nessun caricamento) -------
def engine_status(engine: str, voice: str) -> tuple[bool, str]:
    """(disponibile, dettaglio) SENZA effetti collaterali: solo import e file."""
    if engine == "kitten":
        try:
            import kittentts  # noqa: F401
        except ImportError:
            return False, "pacchetto kittentts non installato (submodule + make install)"
        return True, "pronto (il modello si scarica da HuggingFace al primo uso)"
    if engine == "piper":
        try:
            import piper  # noqa: F401
        except ImportError:
            return False, "pacchetto piper-tts non installato (`pip install piper-tts`, GPL-3)"
        if _piper_voice_files(voice).exists():
            return True, "pronto (voce già scaricata)"
        return True, "pronto (la voce si scarica da HuggingFace al primo uso)"
    return False, f"motore sconosciuto: {engine}"


# ----- Servizio -------------------------------------------------------------------
def synthesize(db: Session, text: str, lang: str | None = None, speed: float | None = None):
    """Sintetizza ``text`` nella lingua data e restituisce il percorso del WAV.

    La cache su disco è indicizzata da (motore, voce, velocità, testo): stessa
    frase → stesso file, sintetizzato una volta sola. Solleva :class:`TtsError`
    con lo status HTTP adatto (400 input, 503 motore non disponibile).
    """
    if not settings_service.get(db, "tts.enabled"):
        raise TtsError(503, "Sintesi vocale disattivata dal super admin (tts.enabled)")
    text = " ".join((text or "").split())  # normalizza gli spazi (chiave di cache stabile)
    if not text:
        raise TtsError(400, "Testo mancante")
    max_chars = int(settings_service.get(db, "tts.max_chars"))
    if len(text) > max_chars:
        raise TtsError(400, f"Testo troppo lungo ({len(text)} > {max_chars} caratteri)")

    lang = (lang or settings_service.get(db, "tts.default_lang") or "it").lower()
    if lang not in LANG_SETTINGS:
        supported = ", ".join(sorted(LANG_SETTINGS))
        raise TtsError(400, f"Lingua «{lang}» non supportata (disponibili: {supported})")
    engine, voice = parse_voice_spec(settings_service.get(db, LANG_SETTINGS[lang]))
    if speed is None:
        speed = float(settings_service.get(db, "tts.speed"))
    speed = max(0.25, min(4.0, float(speed)))

    key = hashlib.sha256(f"{engine}|{voice}|{speed:.2f}|{text}".encode()).hexdigest()
    out_path = cache_dir() / f"{key}.wav"
    if out_path.exists():
        return out_path
    cache_dir().mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".tmp.wav")
    with _synth_lock:
        if out_path.exists():  # sintetizzato da un'altra richiesta nel frattempo
            return out_path
        try:
            ENGINES[engine](text, voice, speed, tmp_path)
        except TtsError:
            tmp_path.unlink(missing_ok=True)
            raise
        except Exception as exc:  # qualunque incidente del motore → 503 spiegato
            tmp_path.unlink(missing_ok=True)
            raise TtsError(503, f"Sintesi fallita ({engine}/{voice}): {exc}") from exc
        tmp_path.rename(out_path)  # pubblicazione atomica: mai WAV a metà in cache
    return out_path


def status(db: Session) -> dict:
    """Stato del servizio per lingua + statistiche cache (per admin e tutorial)."""
    langs = {}
    for lang, key in LANG_SETTINGS.items():
        spec = settings_service.get(db, key)
        try:
            engine, voice = parse_voice_spec(spec)
            ok, detail = engine_status(engine, voice)
        except TtsError as exc:
            engine, voice, ok, detail = None, spec, False, exc.detail
        langs[lang] = {
            "engine": engine,
            "voice": voice,
            "available": ok,
            "detail": detail,
        }
    files = list(cache_dir().glob("*.wav")) if cache_dir().exists() else []
    return {
        "enabled": bool(settings_service.get(db, "tts.enabled")),
        "default_lang": settings_service.get(db, "tts.default_lang"),
        "speed": settings_service.get(db, "tts.speed"),
        "langs": langs,
        "cache": {"files": len(files), "bytes": sum(f.stat().st_size for f in files)},
    }
