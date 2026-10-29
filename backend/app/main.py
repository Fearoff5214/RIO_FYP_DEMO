"""
Novaliseo FastAPI application entry point.
All routes registered under /api/v1.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_config
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    logger.info('"event":"startup","mode":"%s"', get_config().mode)
    # Create tables (dev only; use Alembic in production)
    from app.db.session import create_tables
    await create_tables()
    # Seed demo data if empty
    from scripts.seed_demo import seed_if_empty
    try:
        await seed_if_empty()
    except Exception as e:
        logger.warning('"seed_warning":"%s"', str(e))
    yield
    logger.info('"event":"shutdown"')


app = FastAPI(
    title="Novaliseo API",
    description="AI-Driven Quality Inspection & Root Cause Intelligence Platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS (allow frontend dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ──────────────────────────────────────────────────────────
from app.api import auth, jobs, gates, kb, reports, actions, parts, dashboard, audit  # noqa: E402

API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(jobs.router, prefix=API_PREFIX)
app.include_router(gates.router, prefix=API_PREFIX)
app.include_router(kb.router, prefix=API_PREFIX)
app.include_router(reports.router, prefix=API_PREFIX)
app.include_router(actions.router, prefix=API_PREFIX)
app.include_router(parts.router, prefix=API_PREFIX)
app.include_router(dashboard.router, prefix=API_PREFIX)
app.include_router(audit.router, prefix=API_PREFIX)


# ── Health endpoints ──────────────────────────────────────────────────────────

@app.get("/healthz", tags=["ops"])
async def healthz():
    return {"status": "ok"}


@app.get("/readyz", tags=["ops"])
async def readyz():
    from app.db.session import _get_engine
    try:
        engine = _get_engine()
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        return {"status": "not ready", "error": str(e)}


@app.get("/metrics", tags=["ops"])
async def metrics():
    """Prometheus-style text metrics (stub)."""
    return {"info": "Prometheus metrics not yet configured. Connect Prometheus to /metrics"}
