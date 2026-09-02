"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import init_db
from app.routers import players, teams, league, injuries, matches, sync, history, serie_a_injuries, auth, player_merge, team_merge, trades, winter_market, player_stats_archive, awards

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    logger.info("Database initialized")
    # Scheduler: auto-sync every day at 23:00
    scheduler.add_job(
        func=_auto_sync_job,
        trigger="cron",
        hour=23,
        minute=0,
        id="daily_sync",
        replace_existing=True,
    )
    # Scheduler: bollettino infortuni Serie A ogni ora, con la prima
    # esecuzione subito all'avvio invece che dopo un'ora piena — altrimenti
    # un riavvio del container (es. dopo un auto-deploy) resetta il timer e
    # il job può restare silenzioso per ore se i riavvii sono frequenti.
    scheduler.add_job(
        func=_auto_sync_injuries_job,
        trigger="interval",
        hours=1,
        id="injury_sync",
        replace_existing=True,
        next_run_time=datetime.now(),
    )
    scheduler.start()
    logger.info("Scheduler started")
    yield
    # Shutdown
    scheduler.shutdown()


def _auto_sync_job():
    """Scheduled job: sync prices and votes from fantacalcio.it."""
    from app.database import SessionLocal
    from app.services.sync_service import sync_prices, sync_votes
    from app.models.season import Season

    db = SessionLocal()
    try:
        current_season = db.query(Season).filter(Season.is_current == True).first()
        if not current_season:
            logger.warning("No current season found, skipping auto-sync")
            return
        sync_prices(db, current_season.id)
        sync_votes(db, current_season.id)
        logger.info("Auto-sync completed for season %s", current_season.label)
    except Exception as e:
        logger.error("Auto-sync error: %s", e)
    finally:
        db.close()


def _auto_sync_injuries_job():
    """Scheduled job: sync the Serie A injury bulletin from fantacalcio.it."""
    from app.database import SessionLocal
    from app.services.sync_service import sync_serie_a_injuries

    db = SessionLocal()
    try:
        result = sync_serie_a_injuries(db)
        logger.info("Injury bulletin sync completed: %s", result)
    except Exception as e:
        logger.error("Injury bulletin sync error: %s", e)
    finally:
        db.close()


app = FastAPI(
    title="FT Platform API",
    description="Fantacalcio Tamarros — Backend API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for uploaded logos
import os
os.makedirs(settings.upload_folder, exist_ok=True)
app.mount("/static/logos", StaticFiles(directory=settings.upload_folder), name="logos")

# Routers
API_PREFIX = "/api"
app.include_router(players.router, prefix=API_PREFIX)
app.include_router(teams.router, prefix=API_PREFIX)
app.include_router(league.router, prefix=API_PREFIX)
app.include_router(injuries.router, prefix=API_PREFIX)
app.include_router(matches.router, prefix=API_PREFIX)
app.include_router(sync.router, prefix=API_PREFIX)
app.include_router(history.router, prefix=API_PREFIX)
app.include_router(serie_a_injuries.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(player_merge.router, prefix=API_PREFIX)
app.include_router(team_merge.router, prefix=API_PREFIX)
app.include_router(trades.router, prefix=API_PREFIX)
app.include_router(winter_market.router, prefix=API_PREFIX)
app.include_router(player_stats_archive.router, prefix=API_PREFIX)
app.include_router(awards.router, prefix=API_PREFIX)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": settings.app_version}
