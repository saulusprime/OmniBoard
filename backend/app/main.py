"""Applicazione FastAPI: applica le migrazioni, popola i giochi e monta i router."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import i18n, jobqueue, settings_service
from .ai_providers import seed_providers
from .database import SessionLocal
from .db_migrate import run_migrations
from .routers import (
    admin,
    arena,
    auth,
    community,
    config,
    games,
    groups,
    lessons,
    matches,
    rankings,
    sessions,
    tts,
    users,
)
from .seed import seed_games
from .settings_service import seed_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lo schema è governato dalle migrazioni Alembic (backend/migrations/):
    # l'avvio porta il database alla revisione più recente.
    run_migrations()
    db = SessionLocal()
    try:
        seed_games(db)
        seed_settings(db)
        seed_providers(db)
        # Coda delle mosse IA: pool limitato + RIPRESA delle partite rimaste al
        # turno dell'IA (prima restavano ferme finché un client non le guardava).
        if os.getenv("AI_ASYNC", "1") != "0":
            jobqueue.start(int(settings_service.get(db, "ai.workers")))
            resumed = jobqueue.recovery_scan(db)
            if resumed:
                logger.info("Coda IA: riprese %s partite al turno dell'IA", resumed)
    finally:
        db.close()
    yield


logger = logging.getLogger(__name__)

app = FastAPI(
    title="OmniBoard API",
    description="Backend della piattaforma di giochi da tavolo a turni.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def language_middleware(request, call_next):
    """La lingua della risposta segue l'Accept-Language della richiesta (i18n)."""
    token = i18n.set_language(i18n.parse_accept_language(request.headers.get("accept-language")))
    try:
        return await call_next(request)
    finally:
        i18n.reset_language(token)


app.include_router(users.router)
app.include_router(auth.router)
app.include_router(community.router)
app.include_router(games.router)
app.include_router(groups.router)
app.include_router(matches.router)
app.include_router(sessions.router)
app.include_router(rankings.router)
app.include_router(arena.router)
app.include_router(admin.router)
app.include_router(config.router)
app.include_router(tts.router)
app.include_router(lessons.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
