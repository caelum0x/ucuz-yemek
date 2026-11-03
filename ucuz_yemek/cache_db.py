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
