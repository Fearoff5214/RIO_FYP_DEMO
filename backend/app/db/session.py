"""Async SQLAlchemy session factory."""
from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_config

_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        cfg = get_config()
        _engine = create_async_engine(
            cfg.database_url,
            echo=False,
            future=True,
            connect_args={"check_same_thread": False} if "sqlite" in cfg.database_url else {},
        )
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    """Create all tables (dev/test only; use Alembic in production)."""
    from app.db.models import Base
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(sync_conn) -> None:
    """Lightweight migration for dev databases created before a column existed.
    Adds nullable columns only; production should use Alembic."""
    from sqlalchemy import inspect, text

    from app.db.models import Base

    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        have = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in have and column.nullable:
                ddl = column.type.compile(dialect=sync_conn.dialect)
                sync_conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl}'))
