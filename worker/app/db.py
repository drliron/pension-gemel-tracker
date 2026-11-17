"""שכבת SQLite מקומית. כל הנתונים האישיים נשמרים כאן בלבד."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS fund_tracks (
    track_key TEXT PRIMARY KEY,
    cma_fund_code TEXT NOT NULL,
    cma_track_code TEXT NOT NULL,
    fund_name TEXT NOT NULL,
    track_name TEXT NOT NULL,
    product_type TEXT NOT NULL,
    age_group TEXT NOT NULL DEFAULT 'unknown',
    aliases_json TEXT NOT NULL DEFAULT '[]',
    is_fixture INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS holdings (
    holding_id TEXT PRIMARY KEY,
    track_key TEXT NOT NULL REFERENCES fund_tracks(track_key),
    status TEXT NOT NULL CHECK (status IN ('active','closed')),
    opened_on TEXT,
    closed_on TEXT,
    label TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS statements (
    statement_id TEXT PRIMARY KEY,
    holding_id TEXT NOT NULL REFERENCES holdings(holding_id),
    as_of TEXT NOT NULL,
    balance_ils REAL NOT NULL,
    deposits_ytd_ils REAL,
    monthly_deposit_ils REAL,
    fee_deposit_pct REAL,
    fee_accum_pct REAL,
    reported_track_name TEXT NOT NULL DEFAULT '',
    matched_track_key TEXT,
    source_sha256 TEXT NOT NULL,
    parser_name TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    parser_confidence REAL NOT NULL,
    redactions_json TEXT NOT NULL DEFAULT '{}',
    user_confirmed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS transitions (
    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
    holding_id TEXT NOT NULL REFERENCES holdings(holding_id),
    from_track_key TEXT NOT NULL,
    to_track_key TEXT NOT NULL,
    effective_on TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    UNIQUE (holding_id, from_track_key, to_track_key, effective_on)
);
CREATE TABLE IF NOT EXISTS market_points (
    track_key TEXT NOT NULL,
    period TEXT NOT NULL,
    source_id TEXT NOT NULL,
    monthly_return_pct REAL NOT NULL,
    ytd_return_pct REAL,
    return_12m_pct REAL,
    return_3y_pct REAL,
    return_5y_pct REAL,
    sharpe_5y REAL,
    fee_deposit_pct REAL,
    fee_accum_pct REAL,
    assets_ils_k REAL,
    asset_mix_json TEXT NOT NULL DEFAULT '{}',
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (track_key, period, source_id)
);
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    base_url TEXT NOT NULL DEFAULT '',
    automation_allowed INTEGER NOT NULL DEFAULT 0,
    terms_reviewed_on TEXT,
    min_seconds_between_requests INTEGER NOT NULL DEFAULT 5,
    ttl_hours INTEGER NOT NULL DEFAULT 24
);
CREATE TABLE IF NOT EXISTS cache_entries (
    cache_key TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    url TEXT NOT NULL,
    etag TEXT,
    last_modified TEXT,
    fetched_at TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    body_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('fresh','stale','error'))
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn


def rows(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict]:
    out = []
    for r in conn.execute(sql, args).fetchall():
        d = dict(r)
        for k in list(d):
            if k.endswith("_json") and isinstance(d[k], str):
                d[k[:-5]] = json.loads(d[k])
                del d[k]
        out.append(d)
    return out


def one(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> dict | None:
    r = rows(conn, sql, args)
    return r[0] if r else None
