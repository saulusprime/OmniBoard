"""Applicazione FastAPI: crea le tabelle, popola i giochi e monta i router."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .database import Base, SessionLocal, engine
from .routers import admin, config, games, groups, matches, rankings, sessions, users
from .seed import seed_games
from .settings_service import seed_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Per lo scaffold creiamo le tabelle direttamente; in seguito si userà Alembic.
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_games(db)
        seed_settings(db)
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
app.include_router(games.router)
app.include_router(groups.router)
app.include_router(matches.router)
app.include_router(sessions.router)
app.include_router(rankings.router)
app.include_router(admin.router)
app.include_router(config.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
