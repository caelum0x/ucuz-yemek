"""
Real Postgres-backed cache store -- the thing that was missing before this
pass: `api/index.py` (Vercel) and the CLI both live-called Trendyol
Go/Yemeksepeti on every single request, with no persistence anywhere. This
module is the connection + schema layer for a real cache; `cached_fetchers.py`
is the read-through/write-back logic that uses it, and `refresh_job.py` is
the scheduled job that keeps it warm.

Deliberately NOT wired into the existing Vercel `api/index.py` or the CLI's
default path in this pass -- both keep their exact current behavior
unchanged (see budget.py's new `use_cache` parameter, which defaults to
False). This is additive infrastructure for the new standalone
`backend/server.py` service, not a silent behavior change to what's already
live in production.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg

DEFAULT_DATABASE_URL = "postgresql://ucuz_yemek:ucuz_yemek@localhost:15544/ucuz_yemek"


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    """One real Postgres connection per call -- a small-scale v1 (no pool),
    matching this backend's current single-process scheduled-job scale. A
    real connection pool (psycopg_pool) is the natural upgrade once this
    backend serves meaningfully concurrent request volume."""
    conn = psycopg.connect(_database_url())
    try:
        yield conn
    finally:
        conn.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trendyol_restaurant_search_cache (
    cache_key TEXT PRIMARY KEY,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    restaurants JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trendyol_menu_cache (
    restaurant_id TEXT PRIMARY KEY,
    restaurant_name TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    menu JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS yemeksepeti_chain_cache (
    chain TEXT PRIMARY KEY,
    restaurant_url TEXT,
    items JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def init_schema() -> None:
    """Real `CREATE TABLE IF NOT EXISTS` -- idempotent, safe to call on every
    backend process startup (see backend/server.py's lifespan hook)."""
    with get_connection() as conn:
        conn.execute(SCHEMA_SQL)
        conn.commit()


_HEALTH_TABLES: tuple[str, ...] = (
    "trendyol_restaurant_search_cache",
    "trendyol_menu_cache",
    "yemeksepeti_chain_cache",
)


def cache_health() -> dict[str, Any]:
    """Real row counts + most recent `fetched_at` per cache table --
    exposed via /api/stats (ucuz_yemek/json_api.py) so a caller can see the
    actual, current state of the warm cache (how many real restaurant
    searches/menus/chains are cached, how fresh they are) rather than a
    fabricated number. Raises on a real connection failure (e.g. no
    DATABASE_URL reachable, as in local dev / the stateless Vercel
    deployment) -- the caller decides how to degrade, this function never
    returns fake zeros to paper over an unreachable database."""
    with get_connection() as conn:
        tables: dict[str, Any] = {}
        for table in _HEALTH_TABLES:
            row = conn.execute(f"SELECT count(*), max(fetched_at) FROM {table}").fetchone()  # noqa: S608 -- table name is one of the fixed literals in _HEALTH_TABLES, never user input
            row_count, most_recent_fetch = row if row is not None else (0, None)
            tables[table] = {
                "rows": row_count,
                "most_recent_fetch": most_recent_fetch.isoformat() if most_recent_fetch is not None else None,
            }
        return tables
