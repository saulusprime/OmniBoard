"""Applicazione FastAPI: applica le migrazioni, popola i giochi e monta i router."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .ai_providers import seed_providers
from .database import SessionLocal
from .db_migrate import run_migrations
from .routers import (
    admin,
    auth,
    community,
    config,
    games,
    groups,
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
    finally:
        db.close()
    yield


app = FastAPI(
    title="Scacchi API",
    description="Backend della piattaforma di giochi da tavolo a turni.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(users.router)
app.include_router(auth.router)
app.include_router(community.router)
app.include_router(games.router)
app.include_router(groups.router)
app.include_router(matches.router)
app.include_router(sessions.router)
app.include_router(rankings.router)
app.include_router(admin.router)
app.include_router(config.router)
app.include_router(tts.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
