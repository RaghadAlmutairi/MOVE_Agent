# -*- coding: utf-8 -*-
"""Long-term memory / storage service (SQLite, stdlib only).

Persists every completed run: companies, research_runs, strategy_runs,
content_runs, approvals, execution_logs. Import-safe and fail-soft - storage
errors never break the pipeline.
"""
import os
import json
import sqlite3
import datetime
from typing import Any, Dict, List, Optional

from core.config import STORAGE_DB

_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE, url TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS research_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER, query TEXT, report_json TEXT,
    confidence TEXT, n_sources INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS strategy_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER, research_run_id INTEGER, strategy_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS content_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER, research_run_id INTEGER, content_json TEXT,
    phase TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER, research_run_id INTEGER, decision TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS execution_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER, research_run_id INTEGER, message TEXT, created_at TEXT);
"""


def _now() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="seconds")


def _conn() -> sqlite3.Connection:
    path = STORAGE_DB
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    c = sqlite3.connect(path)
    c.executescript(_SCHEMA)
    return c


def save_run(result: Dict[str, Any], logs: Optional[List[str]] = None) -> Optional[int]:
    """Persist a completed pipeline run. Returns research_run_id (or None)."""
    try:
        plan = result.get("plan", {}) or {}
        report = result.get("report", {}) or {}
        company = plan.get("subject_entity") or report.get("title") or "(market)"
        now = _now()
        with _conn() as c:
            cur = c.cursor()
            cur.execute("INSERT INTO companies(name,url,created_at) VALUES(?,?,?) "
                        "ON CONFLICT(name) DO UPDATE SET url=excluded.url",
                        (company, result.get("url", ""), now))
            cur.execute("SELECT id FROM companies WHERE name=?", (company,))
            cid = cur.fetchone()[0]
            cur.execute("INSERT INTO research_runs(company_id,query,report_json,"
                        "confidence,n_sources,created_at) VALUES(?,?,?,?,?,?)",
                        (cid, result.get("query", ""), json.dumps(report),
                         report.get("confidence_level", ""),
                         len(result.get("sources", [])), now))
            rid = cur.lastrowid
            if result.get("gtm_strategy"):
                cur.execute("INSERT INTO strategy_runs(company_id,research_run_id,"
                            "strategy_json,created_at) VALUES(?,?,?,?)",
                            (cid, rid, json.dumps(result["gtm_strategy"]), now))
            if result.get("content"):
                cur.execute("INSERT INTO content_runs(company_id,research_run_id,"
                            "content_json,phase,created_at) VALUES(?,?,?,?,?)",
                            (cid, rid, json.dumps(result["content"]),
                             result["content"].get("phase", "A"), now))
            for msg in (logs or []):
                cur.execute("INSERT INTO execution_logs(company_id,research_run_id,"
                            "message,created_at) VALUES(?,?,?,?)", (cid, rid, str(msg), now))
        print(f"      [memory] run #{rid} saved for '{company}' -> {STORAGE_DB}")
        return rid
    except Exception as e:
        print(f"      [memory] save skipped: {str(e)[:90]}")
        return None


def log_approval(company: str, decision: str, research_run_id: Optional[int] = None) -> None:
    try:
        with _conn() as c:
            cur = c.cursor()
            cur.execute("SELECT id FROM companies WHERE name=?", (company,))
            row = cur.fetchone()
            cid = row[0] if row else None
            cur.execute("INSERT INTO approvals(company_id,research_run_id,decision,"
                        "created_at) VALUES(?,?,?,?)", (cid, research_run_id, decision, _now()))
    except Exception as e:
        print(f"      [memory] approval log skipped: {str(e)[:80]}")


def recent_runs(limit: int = 5) -> List[Dict[str, Any]]:
    try:
        with _conn() as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                "SELECT r.id, co.name, r.query, r.confidence, r.created_at "
                "FROM research_runs r JOIN companies co ON co.id=r.company_id "
                "ORDER BY r.id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(x) for x in rows]
    except Exception:
        return []
