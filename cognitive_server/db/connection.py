"""
asyncpg connection pool management for the Cognitive MCP server.

A single pool is created on first use and reused for the lifetime of the
process.  Callers acquire connections via the ``get_pool()`` helper or use
``acquire()`` as an async context manager.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
import structlog

log = structlog.get_logger("cognitive.db.connection")

# Module-level singleton pool — initialised lazily.
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return (creating if necessary) the shared asyncpg connection pool.

    The ``DATABASE_URL`` environment variable must be set to a valid
    PostgreSQL / TimescaleDB connection string, e.g.::

        postgresql://user:password@host:5432/dbname
    """
    global _pool
    if _pool is None:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL environment variable is not set. "
                "Provide a PostgreSQL connection string."
            )
        log.info("cognitive_db_pool_creating", database_url=database_url.split("@")[-1])
        _pool = await asyncpg.create_pool(
            dsn=database_url,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        log.info("cognitive_db_pool_ready")
    return _pool


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    """Async context manager that yields a pooled connection.

    Example::

        async with acquire() as conn:
            rows = await conn.fetch("SELECT * FROM pm_interactions LIMIT 10")
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def close_pool() -> None:
    """Gracefully close the connection pool (called on shutdown)."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        log.info("cognitive_db_pool_closed")
