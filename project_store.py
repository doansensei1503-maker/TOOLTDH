"""P1 project/run store: modular monolith, SQLite, no AI, offline replay."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.environ.get("P1_DB_PATH", "data/state/p1_projects.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  topic TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  version TEXT NOT NULL,
  version_no INTEGER NOT NULL,
  status TEXT NOT NULL,
  filters_json TEXT NOT NULL DEFAULT '{}',
  queries_json TEXT NOT NULL DEFAULT '[]',
  funnel_json TEXT NOT NULL DEFAULT '{}',
  top5_json TEXT NOT NULL DEFAULT '[]',
  snapshot_json TEXT NOT NULL DEFAULT '{}',
  idempotency_key TEXT UNIQUE,
  created_at TEXT NOT NULL,
  UNIQUE(project_id, version)
);
CREATE TABLE IF NOT EXISTS videos (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runs(id),
  project_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  canonical_key TEXT NOT NULL DEFAULT '',
  creator TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  views INTEGER NOT NULL DEFAULT 0,
  likes INTEGER NOT NULL DEFAULT 0,
  comments INTEGER NOT NULL DEFAULT 0,
  shares INTEGER NOT NULL DEFAULT 0,
  duration REAL NOT NULL DEFAULT 0,
  posted_at TEXT NOT NULL DEFAULT '',
  age_days INTEGER,
  score INTEGER NOT NULL DEFAULT 0,
  relevance INTEGER NOT NULL DEFAULT 0,
  trend INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'NEEDS_REVIEW',
  certainty TEXT NOT NULL DEFAULT 'UNKNOWN',
  rights TEXT NOT NULL DEFAULT 'UNKNOWN',
  reason TEXT NOT NULL DEFAULT '',
  evidence TEXT NOT NULL DEFAULT '',
  rank INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS media_assets (
  id TEXT PRIMARY KEY,
  video_id TEXT NOT NULL,
  project_id TEXT NOT NULL DEFAULT '',
  run_id TEXT NOT NULL DEFAULT '',
  local_path TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'PLANNED',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS publication_jobs (
  id TEXT PRIMARY KEY,
  video_id TEXT NOT NULL,
  project_id TEXT NOT NULL DEFAULT '',
  run_id TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'PLANNED',
  scheduled_at TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _nid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path = DB_PATH) -> Path:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return Path(db_path)


def create_project(name: str, topic: str, db_path: Path = DB_PATH) -> dict:
    name = str(name or "").strip() or str(topic or "").strip()
    topic = str(topic or "").strip() or name
    if not topic:
        raise ValueError("topic is required")
    init_db(db_path)
    conn = connect(db_path)
    try:
        pid = _nid("proj")
        row = {"id": pid, "name": name, "topic": topic, "created_at": _now()}
        conn.execute(
            "INSERT INTO projects(id,name,topic,created_at) VALUES(?,?,?,?)",
            (pid, name, topic, row["created_at"]),
        )
        conn.commit()
        return row
    finally:
        conn.close()


def list_projects(db_path: Path = DB_PATH) -> list[dict]:
    init_db(db_path)
    conn = connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def next_version(project_id: str, db_path: Path = DB_PATH) -> tuple[str, int]:
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT MAX(version_no) AS m FROM runs WHERE project_id=?", (project_id,)
        ).fetchone()
        nxt = int(row["m"] or 0) + 1
        return (f"v{nxt:03d}", nxt)
    finally:
        conn.close()


def get_run_by_key(idempotency_key: str, db_path: Path = DB_PATH) -> dict | None:
    if not idempotency_key:
        return None
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM runs WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_run(
    project_id: str,
    *,
    filters: dict,
    queries: list[str],
    funnel: dict,
    top5: list[dict],
    videos: list[dict],
    status: str = "COMPLETED",
    idempotency_key: str = "",
    snapshot_extra: dict | None = None,
    db_path: Path = DB_PATH,
) -> dict:
    """Create one immutable run version. Idempotent on idempotency_key.

    ``snapshot_extra`` extends the stored snapshot with the full research
    dataset (the query plan, the candidate pool, the filter decisions, the
    per-query diagnostics and the scoring evidence). It is stored inside the
    existing ``snapshot_json`` column, so no schema migration is needed and
    historical runs stay readable.
    """
    init_db(db_path)
    if idempotency_key:
        existing = get_run_by_key(idempotency_key, db_path)
        if existing:
            return {"run": existing, "deduplicated": True}
    version, version_no = next_version(project_id, db_path)
    conn = connect(db_path)
    try:
        rid = _nid("run")
        snapshot = {
            "project_id": project_id,
            "version": version,
            "queries": queries,
            "filters": filters,
            "funnel": funnel,
            "top5": top5,
        }
        # The extra research dataset is merged in, never replacing a key the
        # historical contract already uses.
        for key, value in (snapshot_extra or {}).items():
            if key in ("project_id", "version", "queries", "filters", "funnel", "top5"):
                continue
            snapshot[key] = value
        conn.execute(
            "INSERT INTO runs(id,project_id,version,version_no,status,filters_json,"
            "queries_json,funnel_json,top5_json,snapshot_json,idempotency_key,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                rid, project_id, version, version_no, status,
                json.dumps(filters or {}, ensure_ascii=False),
                json.dumps(queries or [], ensure_ascii=False),
                json.dumps(funnel or {}, ensure_ascii=False),
                json.dumps(top5 or [], ensure_ascii=False),
                json.dumps(snapshot, ensure_ascii=False),
                idempotency_key or None,
                _now(),
            ),
        )
        for rank, v in enumerate(videos or [], start=1):
            vid = str(v.get("id") or _nid("vid"))
            conn.execute(
                "INSERT INTO videos(id,run_id,project_id,source_url,canonical_key,creator,"
                "title,views,likes,comments,shares,duration,posted_at,age_days,score,"
                "relevance,trend,status,certainty,rights,reason,evidence,rank)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    vid, rid, project_id, str(v.get("source_url", "")),
                    str(v.get("canonical_key", "")), str(v.get("creator", "")),
                    str(v.get("title", "")[:300]), int(v.get("views", 0) or 0),
                    int(v.get("likes", 0) or 0), int(v.get("comments", 0) or 0),
                    int(v.get("shares", 0) or 0), float(v.get("duration_seconds", 0) or v.get("duration", 0) or 0),
                    str(v.get("posted_at", "")), v.get("age_days"),
                    int(v.get("score", 0) or 0), int(v.get("relevance", 0) or 0),
                    int(v.get("trend", 0) or 0), str(v.get("status", "NEEDS_REVIEW")),
                    str(v.get("certainty", "UNKNOWN")), str(v.get("rights", "UNKNOWN")),
                    str(v.get("reason", "")[:500]), str(v.get("evidence", "")[:500]), rank,
                ),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        return {"run": dict(row), "deduplicated": False}
    finally:
        conn.close()


def list_runs(project_id: str, db_path: Path = DB_PATH) -> list[dict]:
    init_db(db_path)
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM runs WHERE project_id=? ORDER BY version_no ASC", (project_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_run(run_id: str, db_path: Path = DB_PATH) -> dict:
    """Offline replay: read snapshot from SQLite only, never network."""
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise KeyError("run not found")
        run = dict(row)
        vids = conn.execute(
            "SELECT * FROM videos WHERE run_id=? ORDER BY rank ASC", (run_id,)
        ).fetchall()
        run["videos"] = [dict(v) for v in vids]
        return run
    finally:
        conn.close()
